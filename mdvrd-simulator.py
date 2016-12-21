#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import sys
import os
import json
import datetime
import argparse
import pprint
import socket
import struct
import functools
import uuid
import random
import math
import addict
import cairo
import shutil
import copy
from PIL import Image



NO_ROUTER = 3

SIMULATION_TIME_SEC = 60 * 60

TX_INTERVAL = 30
TX_INTERVAL_JITTER = int(TX_INTERVAL / 4)
DEAD_INTERVAL = TX_INTERVAL * 3 + 1

# two stiched images result in 1080p resoltion
SIMU_AREA_X = 10 # 960
SIMU_AREA_Y = 10 # 1080

DEFAULT_PACKET_TTL = 16

random.seed(1)

# statitics variables follows
NEIGHBOR_INFO_ACTIVE = 0

PATH_LOGS = "logs"
PATH_IMAGES_RANGE = "images-range"
PATH_IMAGES_TX    = "images-tx"
PATH_IMAGES_MERGE = "images-merge"




class Router:

    class MobilityModel:

        LEFT = 1
        RIGHT = 2
        UPWARDS = 1
        DOWNWARDS = 2

        def __init__(self):
            self.direction_x = random.randint(0, 2)
            self.direction_y = random.randint(0, 2)
            self.velocity = random.randint(1, 1)


        def _move_x(self, x):
            if self.direction_x == Router.MobilityModel.LEFT:
                x -= self.velocity
                if x <= 0:
                    self.direction_x = Router.MobilityModel.RIGHT
                    x = 0
            elif self.direction_x == Router.MobilityModel.RIGHT:
                x += self.velocity
                if x >= SIMU_AREA_X:
                    self.direction_x = Router.MobilityModel.LEFT
                    x = SIMU_AREA_X
            else:
                pass
            return x


        def _move_y(self, y):
            if self.direction_y == Router.MobilityModel.DOWNWARDS:
                y += self.velocity
                if y >= SIMU_AREA_Y:
                    self.direction_y = Router.MobilityModel.UPWARDS
                    y = SIMU_AREA_Y
            elif self.direction_y == Router.MobilityModel.UPWARDS:
                y -= self.velocity
                if y <= 0:
                    self.direction_y = Router.MobilityModel.DOWNWARDS
                    y = 0
            else:
                pass
            return y


        def move(self, x, y):
            x = self._move_x(x)
            y = self._move_y(y)
            return x, y


    def __init__(self, id, ti, prefix_v4):
        self.id = str(id)
        self._init_log()
        self.ti = ti
        self.prefix_v4 = prefix_v4
        self.pos_x = random.randint(0, SIMU_AREA_X)
        self.pos_y = random.randint(0, SIMU_AREA_Y)
        self.time = 0
        self._print_log_header()

        self._init_terminals_data()
        self._calc_next_tx_time()
        self.mm = Router.MobilityModel()
        self.transmitted_now = False
        self.fib = dict()
        self.route_rx_data = dict()
        for interface in ti:
            self.route_rx_data[interface['path_type']] = dict()


    def _print_log_header(self):
        self._log("Initialize router {}".format(self.id))
        self._log("  v4 prefix:{}".format(self.prefix_v4))


    def _log(self, msg):
        msg = "{:5}: {}\n".format(self.time, msg)
        self._log_fd.write(msg)


    def _init_log(self):
        file_path = os.path.join(PATH_LOGS, "{0:05}.log".format(int(self.id)))
        self._log_fd = open(file_path, 'w')


    def _cmp_dicts(self, dict1, dict2):
        if dict1 == None or dict2 == None: return False
        if type(dict1) is not dict or type(dict2) is not dict: return False
        shared_keys = set(dict2.keys()) & set(dict2.keys())
        if not len(shared_keys) == len(dict1.keys()) and len(shared_keys) == len(dict2.keys()):
            return False
        eq = True
        for key in dict1.keys():
            if type(dict1[key]) is dict:
                if key not in dict2:
                    return False
                else:
                    eq = eq and self._cmp_dicts(dict1[key], dict2[key])
            else:
                if key not in dict2:
                    return False
                else:
                    eq = eq and (dict1[key] == dict2[key])
        return eq


    def _cmp_packets(self, packet1, packet2):
        p1 = copy.deepcopy(packet1)
        p2 = copy.deepcopy(packet2)
        # some data may differ, but the content is identical,
        # zeroize them here out
        p1['sequence-no'] = 0
        p2['sequence-no'] = 0
        return self._cmp_dicts(p1, p2)


    def _calc_next_tx_time(self):
            self._next_tx_time = self.time + TX_INTERVAL + random.randint(0, TX_INTERVAL_JITTER)


    def _sequence_no(self, path_type):
        return self.terminals[path_type].sequence_no


    def _sequence_no_inc(self, path_type):
        self.terminals[path_type].sequence_no += 1


    def _init_terminals_data(self):
        self.terminals = addict.Dict()
        for t in self.ti:
            self.terminals[t['path_type']] = addict.Dict()
            self.terminals[t['path_type']].connections = dict()
            # we initialize and handle as many sequence numbers
            # as interfaces because sequence numbers are interface
            # specific. Think about n interfaces, each with a different
            # transmission interval, thus the sequence number is
            # incremented independently.
            self.terminals[t['path_type']].sequence_no = 0


    def dist_update(self, dist, other):
        """connect is just information base on distance
-           path loss or other effects are modeled afterwards.
           This models the PHY channel somehow."""
        for v in self.ti:
            t = v['path_type']
            max_range = v['range']
            if dist <= max_range:
                #print("{} in range:     {} to {} - {} m via {}".format(t, self.id, other.id, dist, t))
                self.terminals[t].connections[other.id] = other
            else:
                #print("{} out of range: {} to {} - {} m".format(t, self.id, other.id, dist))
                if other.id in self.terminals[t].connections:
                    del self.terminals[t].connections[other.id]


    def _rx_save_routing_data(self, sender, interface, packet):
        route_recalc_required = True
        if not str(sender.id) in self.route_rx_data[interface]:
            # new entry (never seen before) or outdated comes
            # back again
            self.route_rx_data[interface][str(sender.id)] = dict()
            global NEIGHBOR_INFO_ACTIVE
            NEIGHBOR_INFO_ACTIVE += 1
        else:
            self._log("\texisting entry")
            # existing entry from neighbor
            seq_no_last = self.route_rx_data[interface][str(sender.id)]['packet']['sequence-no']
            seq_no_new  = packet['sequence-no']
            if seq_no_new <= seq_no_last:
                print("receive duplicate or outdated route packet -> ignore it")
                route_recalc_required = False
                return route_recalc_required
            data_equal = self._cmp_packets(self.route_rx_data[interface][str(sender.id)]['packet'], packet)
            if data_equal:
                # packet is identical, we must save the last packet (think update sequence no)
                # but a route recalculation is not required
                route_recalc_required = False
        self.route_rx_data[interface][str(sender.id)]['rx-time'] = self.time
        self.route_rx_data[interface][str(sender.id)]['packet'] = packet
        #self.route_rx_data[interface][sender.id]['rx-time'] = self.time
        #self.route_rx_data[interface][sender.id]['packet'] = packet
        #self.route_rx_data[interface]={"{}".format(sender.id):{'rx-time':self.time,
        #                                                       'packet':packet}}
        pprint.pprint(self.route_rx_data)

        # for now recalculate route table at every received packet, later we
        # will only recalculate when data has changed
        return route_recalc_required


    def _check_outdated_route_entries(self):
        route_recalc_required = False
        for interface, v in self.route_rx_data.items():
            dellist = []
            for router_id, vv in v.items():
                if self.time - vv["rx-time"] > DEAD_INTERVAL:
                    msg = "outdated entry from {} received at {}, interface: {} - drop it"
                    self._log(msg.format(router_id, vv["rx-time"], interface))
                    dellist.append(router_id)
            for id in dellist:
                route_recalc_required = True
                del v[id]
                global NEIGHBOR_INFO_ACTIVE
                NEIGHBOR_INFO_ACTIVE -= 1
        return route_recalc_required


    def _recalculate_routing_table(self):
        self._log("recalculate routing table")
        self.fib = dict()
        self.compressedloss=dict()
        self.compressedBW=dict()
        self.fib['low_loss'] = dict()
        self.fib['high_bandwidth'] = dict()
        self.neigh_routing_paths = dict()
        self.neigh_routing_paths['neighs']=dict()
        self.neigh_routing_paths['othernode_paths']=dict()
        self._calc_neigh_routing_paths()
        self._calc_fib()


    def rx_route_packet(self, sender, interface, packet):
        msg = "rx route packet from {}, interface:{}, seq-no:{}"
        self._log(msg.format(sender.id, interface, packet['sequence-no']))
        route_recalc_required = self._rx_save_routing_data(sender, interface, packet)
        if route_recalc_required:
            self._recalculate_routing_table()


    def _lookup(self, dest_id, pathtype):
        if len(self.fib) < 1:
            return None, None
        lookup_data=dict()
        self_id=str(self.id)
        dest_found=False
        self._log(pprint.pformat(self.fib))
        #pprint.pprint(self.fib)
        for key_dest,value_dest in self.fib[pathtype].items():
            if key_dest==dest_id:
               for key_self,value_self in value_dest.items():
                   if key_self==self_id:
                      lookup_data['next-hop']=value_self['next-hop']
                      lookup_data['dest_network']=list()
                      lookup_data['dest_network']=value_self['networks']
                      fullpath_found=False
                      for key_path, value_path in value_self.items():
                          if key_path=='full_path':
                             lookup_data['full_path']=list()
                             lookup_data['full_path']=value_path
                             fullpath_found=True
                             break
                      if fullpath_found==False:
                         lookup_data['full_path']=value_self['paths']
               dest_found=True
               break
        self._log(pprint.pformat(lookup_data))
        #pprint.pprint(lookup_data)
        if len(lookup_data)<=0:
            return None, None

        for key_dest,value_dest in self.fib[pathtype].items():
               if key_dest==lookup_data['next-hop']:
                  for key_self,value_self in value_dest.items():
                      if key_self==self_id:
                         for key_i,value_i in value_self['paths'].items():
                             for key_ii, value_ii in value_i.items():
                                 lookup_data['interface']=key_ii
                                 break

        if dest_found==False:
           self._log('path to {} is not available with this pathtype'.format(dest_id))
           return None, None
        #pprint.pprint(self.fib)
        #print(lookup_data['next-hop'],lookup_data['interface'])
        return lookup_data['next-hop'],lookup_data['interface']


    def _calc_neigh_routing_paths(self):
        for key_i,value_i in self.route_rx_data.items():
            for key_s,value_s in value_i.items():
                self._add_all_neighs(key_i,value_i,key_s,value_s)
                if len(value_s['packet']['routingpaths'])>0:
                   self._add_all_othernodes(key_i,value_i,key_s,value_s)
        self._log(pprint.pformat(self.neigh_routing_paths))
        pprint.pprint(self.neigh_routing_paths)

    def _add_all_neighs(self,key_i,value_i,key_s,value_s):
        found_neigh = False
        if len(self.neigh_routing_paths['neighs']) > 0:
           for key_r,value_r in self.neigh_routing_paths['neighs'].items():
               if key_r == key_s:
                  path_found = False
                  for valuevalue_r in value_r['paths']["{}->{}".format(self.id,key_r)]:
                      if valuevalue_r == key_i:
                         path_found = True
                         break
                  if path_found == False:
                     value_r['paths']["{}->{}".format(self.id,key_r)].append(key_i)
                  found_neigh = True
                  break
           if found_neigh == False:
              self._add_neigh_entries(key_s, key_i, value_s)
        else:
            self._add_neigh_entries(key_s, key_i, value_s)

    def _add_all_othernodes(self,key_i,value_i,key_s,value_s):
        self_id=str(self.id)
        if len(self.neigh_routing_paths['othernode_paths']) > 0:
           found_pathtype=False
           for key_path,value_path in value_s['packet']['routingpaths'].items():
               for key_pathtype,value_pathtype in self.neigh_routing_paths['othernode_paths'].items():
                   if key_path == key_pathtype:
                      found_dest=False
                      for key_dest_r,value_dest_r in value_path.items():
                          if key_dest_r==self_id:
                             self._log("skip self routing {} {}".format(key_dest_r,self_id))
                             self._log(pprint.pformat(value_dest_r))
                          else:
                               for key_dest_n,value_dest_n in value_pathtype.items():
                                   if key_dest_r==key_dest_n:
                                      found_node=False
                                      for key_send,value_send in value_dest_r.items():
                                          if key_send==self_id:
                                             self._log("Existing neighbour {} {}".format(key_send,self_id))
                                             self._log(pprint.pformat(value_send))
                                          else:
                                               for key_node,value_node in value_dest_n.items():
                                                   if key_send == key_node:
                                                      value_node = dict()
                                                      value_node=value_send
                                                      found_node=True
                                                      break
                                               if found_node==False:
                                                  value_dest_n[key_send]=value_send
                                      found_dest=True
                                      break
                               if found_dest==False:
                                  value_pathtype[key_dest_r]=value_dest_r
                      found_pathtype=True
                      break
               if found_pathtype==False:
                  self.neigh_routing_paths['othernode_paths'][key_path]=value_path

        else:
             self._log('Adding first entry')
             self.neigh_routing_paths['othernode_paths'] = value_s['packet']['routingpaths']

    def _add_neigh_entries(self, key_s, key_i, value_s):
        self.neigh_routing_paths['neighs'][key_s] ={'next-hop':key_s,
                                                'networks':value_s['packet']['networks'],
                                                 'paths':{"{}->{}".format(self.id,key_s):[key_i]}
                                               }

        self.neigh_routing_paths['paths']=dict()
        for p in self.ti:
            self.neigh_routing_paths['paths'][p['path_type']] = {'loss':p['loss'],
                                                                  'bandwidth':p['bandwidth']
                                                                }
    def _calc_fib(self):
        import networkx as nx
        G = nx.Graph()
        weigh_loss = dict()
        weigh_bandwidth = dict()
        for key_n,value_n in self.neigh_routing_paths['neighs'].items():
            weigh_loss = self._loss_path_compression(key_n,value_n)
            weigh_bandwidth = self._bandwidth_path_compression(key_n,value_n)
            self.add_loss_entry(key_n,value_n,weigh_loss)
            self.add_bandwidth_entry(key_n,value_n,weigh_bandwidth)
        self.add_fib_lowloss_neighs()
        self.add_fib_highBW_neighs()
        if len(self.neigh_routing_paths['othernode_paths'])>0:
           self._calc_shortestpath_loss(G,nx)
           self._calc_widestpath_BW(G,nx)
        self._log(pprint.pformat(self.fib))
        pprint.pprint(self.fib)

    def _calc_shortestpath_loss(self,G,nx):
        self_id=str(self.id)
        dest_array=list()
        for key_neigh,value_neigh in self.compressedloss.items():
            for key_path,value_path in value_neigh[self_id]['paths'].items():
                for key_weigh,value_weigh in value_path.items():
                     G.add_edge(key_neigh,self_id,weight=value_weigh)
        for key_dest,value_dest in self.neigh_routing_paths['othernode_paths']['low_loss'].items():
            for key_node,value_node in value_dest.items():
                if key_node==self_id:
                   self._log("it knows the route only through me so ignore to avoid looping")
                else:
                     for key_path,value_path in value_node['paths'].items():
                         for key_loss,value_loss in value_path.items():
                             if key_path[0]==self_id:
                                self._log("it knows the route only through me so ignore to avoid looping")
                             else:
                                  G.add_edge(key_path[3],key_path[0],weight=value_loss)
            dest_array.append(key_dest)
        for dest in dest_array:
            path_array=list()
            if self_id==dest:
               self._log('source and target are same {}-{}'.format(self_id,dest))
            else:
                 try:
                     path_array = nx.shortest_path(G, dest, self_id, weight='weight')
                 except KeyError:
                     continue
                 except nx.exception.NetworkXNoPath:
                     continue
                 if len(path_array)>2:
                     self.add_shortestloss_path(path_array,self_id)

    def add_shortestloss_path(self,path_array,self_id):
        next_hop_index=(len(path_array))-2
        full_path=path_array[::-1]
        self.fib['low_loss'][path_array[0]]={"{}".format(self.id):{'next-hop':path_array[next_hop_index],
                                                                   'full_path':full_path}}

        for key_i,value_i in self.neigh_routing_paths['othernode_paths']['low_loss'][path_array[0]].items():
            self.fib['low_loss'][path_array[0]][self_id]['networks']=list()
            self.fib['low_loss'][path_array[0]][self_id]['networks']=value_i['networks']
            break
        self.fib['low_loss'][path_array[0]][self_id]['paths']=dict()
        for key_i,value_i in self.neigh_routing_paths['othernode_paths']['low_loss'].items():
            if key_i==path_array[0]:
                for key_j,value_j in value_i.items():
                    if key_j==path_array[next_hop_index]:
                        self.fib['low_loss'][path_array[0]][self_id]['paths']=value_j['paths']
                        break
                break
        #if len(self.fib['low_loss'][path_array[0]][self_id]['paths'])<1:
           #for key_i,value_i in self.neigh_routing_paths['othernode_paths']['low_loss'].items():
               #if key_i==path_array[next_hop_index]:
                  #for key_j,value_j in value_i.items():
                      #if key_j==path_array[0]:
                         #self.fib['low_loss'][path_array[0]][self_id]['paths']=value_j['paths']
                         #break
                  #break

    def _calc_widestpath_BW(self,G,nx):
        self_id=str(self.id)
        dest_array=list()
        for key_neigh,value_neigh in self.compressedBW.items():
            for key_path,value_path in value_neigh[self_id]['paths'].items():
                for key_weigh,value_weigh in value_path.items():
                    G.add_edge(key_neigh,self_id,weight=value_weigh)
        for key_dest,value_dest in self.neigh_routing_paths['othernode_paths']['high_bandwidth'].items():
            for key_node,value_node in value_dest.items():
                if key_node==self_id:
                   self._log("it knows the route only through me so ignore to avoid looping")
                else:
                     for key_path,value_path in value_node['paths'].items():
                         for key_loss,value_loss in value_path.items():
                             if key_path[0]==self_id:
                                self._log("it knows the route only through me so ignore to avoid looping")
                             else:
                                G.add_edge(key_path[3],key_path[0],weight=value_loss)
                                self._log("{} {} {}".format(key_path[0],key_path[3],value_loss))
            dest_array.append(key_dest)
        self._log(dest_array)
        for dest in dest_array:
            path_array=list()
            if self_id==dest:
               self._log('source and target are same {} {}'.format(self_id,dest))
            else:
                 try:
                     path_array = nx.shortest_path(G, dest, self_id, weight='weight')
                 except KeyError:
                     continue
                 except nx.exception.NetworkXNoPath:
                     continue
                 if len(path_array)>2:                                                                                                                      self.add_widestBW_path(path_array,self_id)

    def add_widestBW_path(self,path_array,self_id):
        next_hop_index=(len(path_array))-2
        full_path=path_array[::-1]
        self.fib['high_bandwidth'][path_array[0]]={"{}".format(self.id):{'next-hop':path_array[next_hop_index],
                                                                         'full_path':full_path}}
        for key_i,value_i in self.neigh_routing_paths['othernode_paths']['high_bandwidth'][path_array[0]].items():
            self.fib['high_bandwidth'][path_array[0]][self_id]['networks']=list()
            self.fib['high_bandwidth'][path_array[0]][self_id]['networks']=value_i['networks']
            break
        self.fib['high_bandwidth'][path_array[0]][self_id]['paths']=dict()
        for key_i,value_i in self.neigh_routing_paths['othernode_paths']['high_bandwidth'].items():
            if key_i==path_array[0]:
               for key_j,value_j in value_i.items():
                   if key_j==path_array[next_hop_index]:
                      self.fib['high_bandwidth'][path_array[0]][self_id]['paths']=value_j['paths']
                      break
               break
        #if len(self.fib['high_bandwidth'][path_array[0]][self_id]['paths'])<1:
          # for key_i,value_i in self.neigh_routing_paths['othernode_paths']['high_bandwidth'].items():
               #if key_i==path_array[next_hop_index]:
                  #for key_j,value_j in value_i.items():
                      #if key_j==path_array[0]:
                        # self.fib['high_bandwidth'][path_array[0]][self_id]['paths']=value_j['paths']
                         #break
                  #break

    def add_fib_lowloss_neighs(self):
        if len(self.fib['low_loss'])>0:
           found_dest=False
           for key_node,value_node in self.compressedloss.items():
               for key_dest,value_dest in self.fib['low_loss'].items():
                   if key_dest==key_node:
                      value_dest=dict()
                      value_dest=value_node
                      found_dest=True
                      break
               if found_dest==False:
                  self.fib['low_loss'][key_node]=value_node
        else:
             self.fib['low_loss']=self.compressedloss

    def add_fib_highBW_neighs(self):
        if len(self.fib['high_bandwidth'])>0:
           found_dest=False
           for key_node,value_node in self.compressedloss.items():
               for key_dest,value_dest in self.fib['high_bandwidth'].items():
                   if key_dest==key_node:
                      value_dest=dict()
                      value_dest=value_node
                      found_dest=True
                      break
               if found_dest==False:
                  self.fib['high_bandwidth'][key_node]=value_node
        else:
             self.fib['high_bandwidth']=self.compressedBW

        #pprint.pprint(self.compressedloss)
        #pprint.pprint(self.compressedBW)

    def add_loss_entry(self,key_n,value_n,weigh_loss):
        self.compressedloss[key_n]={"{}".format(self.id):{'next-hop':value_n['next-hop'],
                                     'networks':value_n['networks'],
                                     'paths':{"{}->{}".format(self.id,key_n):dict()},
                                     'paths':{"{}->{}".format(self.id,key_n):weigh_loss}
                                     }}

    def add_bandwidth_entry(self,key_n,value_n,weigh_bandwidth):
        self.compressedBW[key_n]={"{}".format(self.id):{'next-hop':value_n['next-hop'],
                                           'networks':value_n['networks'],
                                           'paths':{"{}->{}".format(self.id,key_n):dict()},
                                           'paths':{"{}->{}".format(self.id,key_n):weigh_bandwidth}
                                           }}

    def _loss_path_compression(self,key_n,value_n):
         loss_dict = dict()
         for key,value in value_n['paths'].items():
             for valuevalue in value:
                 for key_path,value_path in self.neigh_routing_paths['paths'].items():
                     if key_path==valuevalue:
                        if len(loss_dict)>0:
                           for key_l,value_l in loss_dict.items():
                               if value_path['loss']<value_l:
                                  loss_dict=dict()
                                  loss_dict[key_path]=value_path['loss']
                        else:
                           loss_dict[key_path]=value_path['loss']
                        break
         return loss_dict

    def _bandwidth_path_compression(self,key_n,value_n):
         bandwidth_dict = dict()
         for key,value in value_n['paths'].items():
             for valuevalue in value:
                 for key_path,value_path in self.neigh_routing_paths['paths'].items():
                     if key_path==valuevalue:
                        if len(bandwidth_dict)>0:
                           for key_l,value_l in bandwidth_dict.items():
                               if value_path['bandwidth']>value_l:
                                  bandwidth_dict=dict()
                                  bandwidth_dict[key_path]=value_path['bandwidth']
                        else:
                           bandwidth_dict[key_path]=value_path['bandwidth']
                        break
         return bandwidth_dict


    def rx_route_packet(self, sender, interface, packet):
        msg = "rx route packet from {}, interface:{}, seq-no:{}"
        self._log(msg.format(sender.id, interface, packet['sequence-no']))
        #pprint.pprint(packet)
        route_recalc_required = self._rx_save_routing_data(sender, interface, packet)
        if route_recalc_required:
            self._recalculate_routing_table()

    def create_routing_packet(self, path_type):
        packet = dict()
        packet['routingpaths'] = dict()
        packet['router-id'] = self.id
        # add sequence number to packet ..
        packet['sequence-no'] = self._sequence_no(path_type)
        # ... and increment number locally
        self._sequence_no_inc(path_type)
        packet['networks'] = list()
        packet['networks'].append({"v4-prefix" : self.prefix_v4})
        if len(self.fib)>0:
           packet['routingpaths']=self.fib
        return packet


    def tx_route_packet(self):
        # depending on local information the route
        # packets must be generated for each interface
        #print("{} transmit data".format(self.id))
        for v in self.ti:
            interface = v['path_type']
            packet = self.create_routing_packet(interface)
            for other_id, other_router in self.terminals[interface].connections.items():
                """ this is the multicast packet transmission process """
                #print(" to router {} [{}]".format(other_id, t))
                other_router.rx_route_packet(self, interface, packet)


    def forward_data_packet(self, packet):
        packet.ttl -= 0
        if packet.ttl <= 0:
            print("TTL 0 reached, routing loop detected!!!")
            return
        if packet.dst_id == self.id:
            print("REACHED DESTINATION")
            return
        # do a route FIB lookup to each dst_id
        # and forward data to this router. If no
        # route can be found then
        # a) the destination is out of range
        # b) route table has a bug
        dst_id = packet.dst_id
        src_id = packet.src_id
        next_hop_addr,interface = self._lookup(str(dst_id), packet.tos)
        if next_hop_addr == None:
            print("{}: ICMP - no route to host, drop packet".format(self.id))
            return
        print("{}: packet src:{} dst:{}".format(self.id, src_id, dst_id))
        print("  current:{} nexthop: {}".format(self.id, next_hop_addr))
        print("  TOS: {} (packet prefered way)".format(packet.tos))
        # FIXME: use rx_data_packet() instead of ..forward_data_packet
        #print(interface)
        #print(next_hop_addr)
       # pprint.pprint(self.terminals)
        self.terminals[interface].connections[next_hop_addr].forward_data_packet(packet)



    def rx_data_packet(self, sender, interface, packet):
        print("{} receive data packet from {}".format(self.id, sender.id))
        if dst_id == self.id:
            print("FINISH, packet received at destination")
        else:
            if packet.ttl <= 0:
                print("TTL 0 reached, routing loop detected!!!")
                return
            packet.ttl -= 0
            self.forward_data_packet(packet)


    def pos(self):
        return self.pos_x, self.pos_y


    def step(self):
        self.time += 1
        self.pos_x, self.pos_y = self.mm.move(self.pos_x, self.pos_y)
        route_recalc_required = self._check_outdated_route_entries()
        if route_recalc_required:
            self._recalculate_routing_table()

        if self.time == self._next_tx_time:
            self.tx_route_packet()
            self._calc_next_tx_time()
            self.transmitted_now = True
        else:
            self.transmitted_now = False


def rand_ip_prefix(type_):
    if type_ != "v4":
        raise Exception("Only v4 prefixes supported for now")
    addr = random.randint(0, 4000000000)
    a = socket.inet_ntoa(struct.pack("!I", addr))
    b = a.split(".")
    c = "{}.{}.{}.0/24".format(b[0], b[1], b[2])
    return c


def dist_update_all(r):
    for i in range(NO_ROUTER):
        for j in range(NO_ROUTER):
            if i == j: continue
            i_pos = r[i].pos()
            j_pos = r[j].pos()
            dist = math.hypot(i_pos[1] - j_pos[1], i_pos[0] - j_pos[0])
            r[j].dist_update(dist, r[i])


def draw_router_loc(r, path, img_idx):
    c_links = { 'tetra00' : (1.0, 0.15, 0.15, 1.0),  'wifi00' :(0.15, 1.0, 0.15, 1.0)}
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIMU_AREA_X, SIMU_AREA_Y)
    ctx = cairo.Context(surface)
    ctx.rectangle(0, 0, SIMU_AREA_X, SIMU_AREA_Y)
    ctx.set_source_rgba(0.15, 0.15, 0.15, 1.0)
    ctx.fill()

    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        color = ((1.0, 1.0, 0.5, 0.05), (1.0, 0.0, 1.0, 0.05))
        ctx.set_line_width(0.1)
        path_thinkness = 4.0
        # iterate over links
        for i, t in enumerate(router.ti):
            range_ = t['range']
            path_type = t['path_type']
            ctx.set_source_rgba(*color[i])
            ctx.move_to(x, y)
            ctx.arc(x, y, range_, 0, 2 * math.pi)
            ctx.fill()

            # draw lines between links
            ctx.set_line_width(path_thinkness)
            for r_id, other in router.terminals[t['path_type']].connections.items():
                other_x, other_y = other.pos_x, other.pos_y
                ctx.move_to(x, y)
                ctx.set_source_rgba(*c_links[path_type])
                ctx.line_to(other_x, other_y)
                ctx.stroke()
            path_thinkness -= 2.0

    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        # node middle point
        ctx.set_line_width(0.0)
        ctx.set_source_rgb(0.5, 1, 0.5)
        ctx.move_to(x, y)
        ctx.arc(x, y, 5, 0, 2 * math.pi)
        ctx.fill()

        # router id
        ctx.set_font_size(10)
        ctx.set_source_rgb(0.5, 1, 0.7)
        ctx.move_to(x + 10, y + 10)
        ctx.show_text(str(router.id))

        # router IP prefix
        ctx.set_font_size(8)
        ctx.set_source_rgba(0.5, 1, 0.7, 0.5)
        ctx.move_to(x + 10, y + 20)
        ctx.show_text(router.prefix_v4)

    full_path = os.path.join(path, "{0:05}.png".format(img_idx))
    surface.write_to_png(full_path)


def draw_router_transmission(r, path, img_idx):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIMU_AREA_X, SIMU_AREA_Y)
    ctx = cairo.Context(surface)
    ctx.rectangle(0, 0, SIMU_AREA_X, SIMU_AREA_Y)
    ctx.set_source_rgba(0.15, 0.15, 0.15, 1.0)
    ctx.fill()

    # transmitting circles
    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        if router.transmitted_now:
            ctx.set_source_rgba(.10, .10, .10, 1.0)
            ctx.move_to(x, y)
            ctx.arc(x, y, 50, 0, 2 * math.pi)
            ctx.fill()

    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        color = ((1.0, 1.0, 0.5, 0.05), (1.0, 0.0, 1.0, 0.05))
        ctx.set_line_width(0.1)
        path_thinkness = 6.0
        # iterate over links
        for i, t in enumerate(router.ti):
            range_ = t['range']
            path_type = t['path_type']

            # draw lines between links
            ctx.set_line_width(path_thinkness)
            for r_id, other in router.terminals[t['path_type']].connections.items():
                other_x, other_y = other.pos_x, other.pos_y
                ctx.move_to(x, y)
                ctx.set_source_rgba(.0, .0, .0, .4)
                ctx.line_to(other_x, other_y)
                ctx.stroke()

            path_thinkness -= 4.0
            if path_thinkness < 2.0:
                path_thinkness = 2.0

    # draw dots over all
    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        ctx.set_line_width(0.0)
        ctx.set_source_rgb(0, 0, 0)
        ctx.move_to(x, y)
        ctx.arc(x, y, 5, 0, 2 * math.pi)
        ctx.fill()

    full_path = os.path.join(path, "{0:05}.png".format(img_idx))
    surface.write_to_png(full_path)


def image_merge(merge_path, range_path, tx_path, img_idx):

    m_path = os.path.join(merge_path, "{0:05}.png".format(img_idx))
    r_path = os.path.join(range_path, "{0:05}.png".format(img_idx))
    t_path = os.path.join(tx_path,    "{0:05}.png".format(img_idx))

    images = map(Image.open, [r_path, t_path])
    new_im = Image.new('RGB', (1920, 1080))

    x_offset = 0
    for im in images:
        new_im.paste(im, (x_offset,0))
        x_offset += im.size[0]

    new_im.save(m_path, "PNG")


def draw_images(r, img_idx):
    draw_router_loc(r, PATH_IMAGES_RANGE, img_idx)
    draw_router_transmission(r, PATH_IMAGES_TX, img_idx)

    image_merge(PATH_IMAGES_MERGE, PATH_IMAGES_RANGE, PATH_IMAGES_TX, img_idx)


def setup_img_folder():
    for path in (PATH_IMAGES_RANGE, PATH_IMAGES_TX, PATH_IMAGES_MERGE):
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)


def gen_data_packet(src_id, dst_id, tos='low-loss'):
    packet = addict.Dict()
    packet.src_id = src_id
    packet.dst_id = dst_id
    packet.ttl = DEFAULT_PACKET_TTL
    # the prefered transmit is via wifi00, can be tetra if not possible
    packet.tos = tos
    return packet


def setup_log_folder():
    if os.path.exists(PATH_LOGS):
        shutil.rmtree(PATH_LOGS)
    os.makedirs(PATH_LOGS)


def main():
    #setup_img_folder()
    setup_log_folder()

    ti = [ {"path_type": "2", "range" : 50, "bandwidth" : 10000, "loss" : 20},
           {"path_type": "1", "range" : 200, "bandwidth" : 1000, "loss" : 5 },
           {"path_type": "4", "range" : 100, "bandwidth" : 30000, "loss" : 30},
           {"path_type": "3", "range" : 300, "bandwidth" : 2000, "loss" : 10 }  ]

    r = dict()
    for i in range(NO_ROUTER):
        prefix_v4 = rand_ip_prefix('v4')
        r[i] = Router(i, ti, prefix_v4)

    # initial positioning
    dist_update_all(r)

    src_id = random.randint(0, NO_ROUTER - 1)
    dst_id = random.randint(0, NO_ROUTER - 1)
    packet_low_loss       = gen_data_packet(src_id, dst_id, tos='low_loss')
    packet_high_througput = gen_data_packet(src_id, dst_id, tos='high_bandwidth')
    for sec in range(SIMULATION_TIME_SEC):
        sep = '=' * 50
        print("\n{}\nsimulation time:{:6}/{}\n".format(sep, sec, SIMULATION_TIME_SEC))
        for i in range(NO_ROUTER):
            r[i].step()
        dist_update_all(r)
        #draw_images(r, sec)
        # inject test data packet into network
        r[src_id].forward_data_packet(packet_low_loss)
        r[src_id].forward_data_packet(packet_high_througput)

    cmd = "ffmpeg -framerate 10 -pattern_type glob -i 'images-merge/*.png' -c:v libx264 -pix_fmt yuv420p mdvrd.mp4"
    print("now execute \"{}\" to generate a video".format(cmd))


if __name__ == '__main__':
    main()
