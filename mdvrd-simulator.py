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


NO_ROUTER = 50

SIMULATION_TIME_SEC = 60 * 60

TX_INTERVAL = 30
TX_INTERVAL_JITTER = int(TX_INTERVAL / 4)

SIMU_AREA_X = 1000
SIMU_AREA_Y = 1000

random.seed(1)

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
                # none, so no x movement at all
                pass
            return x

        def _move_y(self, y):
            if self.direction_y == Router.MobilityModel.DOWNWARDS:
                y -= self.velocity
                if y <= 0:
                    self.direction_y = Router.MobilityModel.UPWARDS
                    y = 0
            elif self.direction_y == Router.MobilityModel.UPWARDS:
                y += self.velocity
                if y >= SIMU_AREA_Y:
                    self.direction_x = Router.MobilityModel.DOWNWARDS
                    y = SIMU_AREA_Y
            else:
                # none, so no x movement at all
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
        self._init_terminals
        self.terminals = addict.Dict()
        self._calc_next_tx_time()
        self.mm = Router.MobilityModel()
        self.route_rx_data = dict()


    def _calc_next_tx_time(self):
            self._next_tx_time = self.time + TX_INTERVAL + random.randint(0, TX_INTERVAL_JITTER)


    def _init_terminals(self):
        for t in self.ti:
            self.terminals[t['path_type']] = addict.Dict()
            self.terminals[t['path_type']].connections = dict()

    def dist_update(self, dist, other):
        """connect is just information base on distance
           path loss or other effects are modeled afterwards.
           This models the PHY channel somehow."""
        for v in self.ti:
            t = v['path_type']
            max_range = v['range']
            if dist <= max_range:
                #print("{} in range:     {} to {} - {} m".format(t, self.id, other.id, dist))
                self.terminals[t].connections[other.id] = other
            else:
                #print("{} out of range: {} to {} - {} m".format(t, self.id, other.id, dist))
                if other.id in self.terminals[t].connections:
                    del self.terminals[t].connections[other.id]

    def receive(self, sender, packet):
        print("{} receive packet from {}".format(self.id, sender.id))
        pprint.pprint(packet)

    def create_packet(self, path_type):
        packet = dict()
        packet['router-id'] = self.id
        packet['networks'] = list()
        packet['networks'].append({"prefix" : self.prefix})
        return packet

    def _transmit(self):
        #print("{} transmit data".format(self.id))
        for v in self.ti:
            pt = v['path_type']
            for other_id, other_router in self.terminals[pt].connections.items():
                """ this is the multicast packet transmission process """
                #print(" to router {} [{}]".format(other_id, t))
                packet = self.create_packet(pt)
                other_router.receive(self, packet)


    def pos(self):
        return self.pos_x, self.pos_y

    def step(self):
        self.time += 1
        self.pos_x, self.pos_y = self.mm.move(self.pos_x, self.pos_y)
        if self.time == self._next_tx_time:
            self._transmit()
            self._calc_next_tx_time()


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

def draw_router_loc(ctx, x, y):
    ctx.set_line_width(0.5)
    ctx.set_source_rgb(0.5, 1, 0.5)
    ctx.move_to(x, y)
    ctx.arc(x, y, 5, 5, 2 * math.pi)
    ctx.fill()

def main():
    ti = [ {"path_type": "wb", "range" : 100, "bandwidth" : 5000},
           {"path_type": "nb", "range" : 150, "bandwidth" : 1000 } ]

    r = dict()
    for i in range(NO_ROUTER):
        prefix = rand_ip_prefix()
        print(prefix)
        r[i] = Router(i, ti, prefix)

    # initial positioning
    dist_update_all(r)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIMU_AREA_X, SIMU_AREA_Y)
    ctx = cairo.Context(surface)
    #ctx.scale(SIMU_AREA_X, SIMU_AREA_Y)
    ctx.rectangle(0, 0, SIMU_AREA_X, SIMU_AREA_Y)
    ctx.set_source_rgb(0.95, 0.95, 0.95) 
    ctx.fill()

    for sec in range(SIMULATION_TIME_SEC):
        for i in range(NO_ROUTER):
            r[i].step()
            draw_router_loc(ctx, r[i].pos_x, r[i].pos_y)
        dist_update_all(r)

    surface.write_to_png('map.png')


if __name__ == '__main__':
    main()
