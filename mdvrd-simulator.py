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



NO_ROUTER = 100

SIMULATION_TIME_SEC = 60 * 60

TX_INTERVAL = 30
TX_INTERVAL_JITTER = int(TX_INTERVAL / 4)
DEAD_INTERVAL = TX_INTERVAL * 3 + 1

# two stiched images result in 1080p resoltion
SIMU_AREA_X = 960
SIMU_AREA_Y = 1080

DEFAULT_PACKET_TTL = 32

random.seed(1)

# statitics variables follows
NEIGHBOR_INFO_ACTIVE = 0

LOGPATH = "logs"


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


    def __init__(self, id, ti, prefix):
        self.id = id
        self.ti = ti
        self.prefix = prefix
        self.pos_x = random.randint(0, SIMU_AREA_X)
        self.pos_y = random.randint(0, SIMU_AREA_Y)
        self.time = 0

        self._init_log()
        self._init_terminals_data()
        self._calc_next_tx_time()
        self.mm = Router.MobilityModel()
        self.transmitted_now = False

        self.route_rx_data = dict()
        for interface in ti:
            self.route_rx_data[interface['path_type']] = dict()

    def _log(self, msg):
        msg = "{:5}: {}\n".format(self.time, msg)
        self._log_fd.write(msg)

    def _init_log(self):
        file_path = os.path.join(LOGPATH, "{0:05}.log".format(self.id))
        self._log_fd = open(file_path, 'w')

    def _cmp_dicts(dict1, dict2):
        if dict1 == None or dict2 == None: return False
        if type(dict1) is not dict or type(dict2) is not dict: return False
        shared_keys = set(dict2.keys()) & set(dict2.keys())
        if not len(shared_keys) == len(dict1.keys()) and len(shared_keys) == len(dict2.keys()):
            return False
        eq = True
        for key in dict1.keys():
            if type(dict1[key]) is dict:
                eq = eq and compare_dictionaries(dict1[key],dict2[key])
            else:
                eq = eq and (dict1[key] == dict2[key])
        return eq

    def _cmp_packets(packet1, packet2):
        p1 = copy.deepcopy(packet1)
        p2 = copy.deepcopy(packet2)
        # some data may differ, but the content is identical,
        # zeroize them here out
        p1['sequence-no'] = 0
        p2['sequence-no'] = 0
        eq = self._cmp_dicts(p1, p2)
        if eq:
            raise("packet queal")
        return eq

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
           path loss or other effects are modeled afterwards.
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
        if not sender in self.route_rx_data[interface]:
            # new entry (never seen before) or outdated comes
            # back again
            self.route_rx_data[interface][sender.id] = dict()
            global NEIGHBOR_INFO_ACTIVE
            NEIGHBOR_INFO_ACTIVE += 1
        else:
            raise
            # existing entry from neighbor
            seq_no_last = self.route_rx_data[interface][sender.id]['packet']['sequence-no']
            seq_no_new  = packet['sequence-no']
            if seq_no_new <= seq_no_last:
                print("receive duplicate or outdated route packet -> ignore it")
                route_recalc_required = False
                return route_recalc_required
            data_equal = self._cmp_packets(self.route_rx_data[interface][sender.id]['packet'], packet)
            if data_equal:
                # packet is identical, we must save the last packet (think update sequence no)
                # but a route recalculation is not required
                route_recalc_required = False
        self.route_rx_data[interface][sender.id]['rx-time'] = self.time
        self.route_rx_data[interface][sender.id]['packet'] = packet

        # for now recalculate route table at every received packet, later we
        # will only recalculate when data has changed
        return route_recalc_required

    def _check_outdated_route_entries(self):
        route_recalc_required = False
        for interface, v in self.route_rx_data.items():
            dellist = []
            for router_id, vv in v.items():
                if self.time - vv["rx-time"] > DEAD_INTERVAL:
                    msg = "{}: route entry from {} outdated [interface:{}], remove from raw table"
                    self._log("outdated entry from {} received at {}, interface: {}".format(router_id, vv["rx-time"], interface))
                    print(msg.format(self.id, router_id, interface))
                    dellist.append(router_id)
            for id in dellist:
                route_recalc_required = True
                del v[id]
                global NEIGHBOR_INFO_ACTIVE
                NEIGHBOR_INFO_ACTIVE -= 1
        return route_recalc_required

    def _recalculate_routing_table(self):
        # this function is called when
        # a) a new routing packet is received from one of our neighbors
        # b) a particular routing information is outdated and removed from
        #    self.route_rx_data
        # if you have a packet for id 200, then you have one possibility via 23 via interface "wifi00
        # self.fib["200"] = {
        # 			"highest-bandwidth": { "next-hop-id" : 23, "interface" : "wifi00"  },
        # 			"lowest-loss": { "next-hop-id" : 23, "interface" : "tetra00"  }
        # }
        # self.fib["20"] = {
        # 			"highest-bandwidth": { "next-hop-id" : 23, "interface" : "wifi00"  },
        # 			"lowest-loss": { "next-hop-id" : 23, "interface" : "tetra00"  }
        # }
        # self.fib["23"] = {
        # 			"highest-bandwidth": { "next-hop-id" : "direct", "interface" : "wifi00"  },
        # 			"lowest-loss": { "next-hop-id" : "direct", "interface" : "tetra00"  }
        # }
        print("{} recalculate routing table".format(self.id))

    def rx_route_packet(self, sender, interface, packet):
        self._log("rx route packet from {}, interface:{}, seq-no:{}".format(sender.id, interface, packet['sequence-no']))
        print("{} receive routing protocol packet from {}".format(self.id, sender.id))
        print("  rx interface: {}".format(interface))
        print("  sequence no:  {}".format(packet['sequence-no']))
        #pprint.pprint(packet)
        route_recalc_required = self._rx_save_routing_data(sender, interface, packet)
        if route_recalc_required:
            self._recalculate_routing_table()

    def create_routing_packet(self, path_type):
        packet = dict()
        packet['router-id'] = self.id
        # add sequence number to packet ..
        packet['sequence-no'] = self._sequence_no(path_type)
        # ... and increment number locally
        self._sequence_no_inc(path_type)
        packet['networks'] = list()
        packet['networks'].append({"v4-prefix" : self.prefix})
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
        # do a route FIB lookup to each dst_id
        # and forward data to this router. If no
        # route can be found then
        # a) the destination is out of range
        # b) route table has a bug
        dst_id = packet.dst_id
        src_id = packet.src_id
        print("src:{} dst:{}".format(src_id, dst_id))
        print("TOS: {} (packet prefered way)".format(packet.tos))


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


def rand_ip_prefix():
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
        ctx.show_text(router.prefix)

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


PATH_IMAGES_RANGE = "images-range"
PATH_IMAGES_TX    = "images-tx"
PATH_IMAGES_MERGE = "images-merge"


def draw_images(r, img_idx):
    draw_router_loc(r, PATH_IMAGES_RANGE, img_idx)
    draw_router_transmission(r, PATH_IMAGES_TX, img_idx)

    image_merge(PATH_IMAGES_MERGE, PATH_IMAGES_RANGE, PATH_IMAGES_TX, img_idx)

def setup_img_folder():
    for path in (PATH_IMAGES_RANGE, PATH_IMAGES_TX, PATH_IMAGES_MERGE):
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)

def gen_data_packet():
    packet = addict.Dict()
    packet.src_id = random.randint(0, NO_ROUTER - 1)
    packet.dst_id = random.randint(0, NO_ROUTER - 1)
    packet.ttl = DEFAULT_PACKET_TTL
    # the prefered transmit is via wifi00, can be tetra if not possible
    packet.tos = 'low-latency'
    return packet

def setup_log_folder():
    if os.path.exists(LOGPATH):
        shutil.rmtree(LOGPATH)
    os.makedirs(LOGPATH)

def main():
    setup_img_folder()
    setup_log_folder()

    ti = [ {"path_type": "wifi00", "range" : 100, "bandwidth" : 5000},
           {"path_type": "tetra00", "range" : 150, "bandwidth" : 1000 } ]

    r = dict()
    for i in range(NO_ROUTER):
        prefix = rand_ip_prefix()
        print(prefix)
        r[i] = Router(i, ti, prefix)

    # initial positioning
    dist_update_all(r)

    for sec in range(SIMULATION_TIME_SEC):
        sep = '=' * 50
        print("\n{}\nsimulation time:{} of:{}".format(sep, sec, SIMULATION_TIME_SEC))
        for i in range(NO_ROUTER):
            r[i].step()
        dist_update_all(r)
        draw_images(r, sec)
        # inject data packet into network
        packet = gen_data_packet()
        r[packet.src_id].forward_data_packet(packet)
        print("NEIGHBOR INFO ACTIVE: {}".format(NEIGHBOR_INFO_ACTIVE))

    cmd = "ffmpeg -framerate 10 -pattern_type glob -i 'images-merge/*.png' -c:v libx264 -pix_fmt yuv420p out.mp4"
    print("now execute \"{}\" to generate a video".format(cmd))


if __name__ == '__main__':
    main()
