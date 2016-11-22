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

class Router:

    def __init__(self, id, ti, prefix):
        self.id = id
        self.ti = ti
        self.prefix = prefix
        self.pos_x = random.randint(0, 1000)
        self.pos_y = random.randint(0, 1000)
        self.time = 0
        self._init_terminals

    def _init_terminals(self):
        for t in self.ti:
            pass

    def connect(self, dist, router_id):
        print("from {} to {} - {} m".format(self.id, self.router_id, dist))
        for v in self.ti:
            if v["type"] == type:
                v["connections"] = router_id

    def pos(self):
        return self.pos_x, self.pos_y

    def step(self):
        self.time += 1


def rand_ip_prefix():
	addr = random.randint(0, 4000000000)
	a = socket.inet_ntoa(struct.pack("!I", addr))
	b = a.split(".")
	c = "{}.{}.{}.0/24".format(b[0], b[1], b[2])
	return c

def main():
    NO_ROUTER = 100
    NO_TERMINALS = 3

    ti = [ {"type": "wb", "range" : 50, "bandwidth" : 5000},
           {"type": "nb", "range" : 100, "bandwidth" : 1000 } ]

    r = dict()
    for i in range(NO_ROUTER):
        prefix = rand_ip_prefix()
        print(prefix)
        r[i] = Router(i, ti, prefix)

    for i in range(NO_ROUTER):
        for j in range(NO_ROUTER):
            if i == j: continue
            i_pos = r[i].pos()
            j_pos = r[j].pos()
            dist = math.hypot(i_pos[1] - j_pos[1], i_pos[0] - j_pos[0])
            r[j].connect(dist, i)



    for sec in range(60*60):
        for i in range(NO_ROUTER):
            r[i].step()


if __name__ == '__main__':
    main()
