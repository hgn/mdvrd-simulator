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



NO_ROUTER = 50

SIMULATION_TIME_SEC = 60 * 60

TX_INTERVAL = 30
TX_INTERVAL_JITTER = int(TX_INTERVAL / 4)

SIMU_AREA_X = 1000
SIMU_AREA_Y = 1000

class Router:

    class MovementModel:

        LEFT = 1
        RIGHT = 2
        UPWARDS = 1
        DOWNWARDS = 2

        def __init__(self):
            self.direction_x = random.randint(0, 2)
            self.direction_y = random.randint(0, 2)
            self.velocity = random.randint(1, 1)

        def _move_x(self, x):
            if self.direction_x == Router.MovementModel.LEFT:
                x -= self.velocity
                if x <= 0:
                    self.direction_x = Router.MovementModel.RIGHT
                    x = 0
            elif self.direction_x == Router.MovementModel.RIGHT:
                x += self.velocity
                if x >= SIMU_AREA_X:
                    self.direction_x = Router.MovementModel.LEFT
                    x = SIMU_AREA_X
            else:
                # none, so no x movement at all
                pass
            return x

        def _move_y(self, y):
            if self.direction_y == Router.MovementModel.DOWNWARDS:
                y -= self.velocity
                if y <= 0:
                    self.direction_y = Router.MovementModel.UPWARDS
                    y = 0
            elif self.direction_y == Router.MovementModel.UPWARDS:
                y += self.velocity
                if y >= SIMU_AREA_Y:
                    self.direction_x = Router.MovementModel.DOWNWARDS
                    y = SIMU_AREA_Y
            else:
                # none, so no x movement at all
                pass
            return y

        def move(self, x, y):
            x = self._move_x(x)
            y = self._move_x(y)
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
        self.mm = Router.MovementModel()


    def _calc_next_tx_time(self):
            self._next_tx_time = self.time + TX_INTERVAL + random.randint(0, TX_INTERVAL_JITTER)


    def _init_terminals(self):
        for t in self.ti:
            self.terminals[t['type']] = addict.Dict()
            self.terminals[t['type']].connections = dict()

    def dist_update(self, dist, other):
        """connect is just information base on distance
           path loss or other effects are modeled afterwards.
           This models the PHY channel somehow."""
        for v in self.ti:
            t = v['type']
            max_range = v['range']
            if dist <= max_range:
                print("{} in range:     {} to {} - {} m".format(t, self.id, other.id, dist))
                self.terminals[t].connections[other.id] = other
            else:
                print("{} out of range: {} to {} - {} m".format(t, self.id, other.id, dist))
                if other.id in self.terminals[t].connections:
                    del self.terminals[t].connections[other.id]

    def receive(self, sender, packet):
        print("receive packet from {}".format(sender.id))

    def _transmit(self):
        #print("{} transmit data".format(self.id))
        for v in self.ti:
            t = v['type']
            for other_id, other_router in self.terminals[t].connections.items():
                #print(" to router {} [{}]".format(other_id, t))
                packet = {}
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

def main():
    ti = [ {"type": "wb", "range" : 100, "bandwidth" : 5000},
           {"type": "nb", "range" : 150, "bandwidth" : 1000 } ]

    r = dict()
    for i in range(NO_ROUTER):
        prefix = rand_ip_prefix()
        print(prefix)
        r[i] = Router(i, ti, prefix)

    # initial positioning
    dist_update_all(r)


    for sec in range(SIMULATION_TIME_SEC):
        for i in range(NO_ROUTER):
            r[i].step()
        dist_update_all(r)


if __name__ == '__main__':
    main()
