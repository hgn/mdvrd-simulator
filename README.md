# Policy Multipath Routing Daemon (MRD) - Simulator #


# Nomenclature #

## Raw Table ##

This is the table where the received protocol messages from the neighbors are
stored. They are never touched or modified in any way. The simple save the raw
data, thus the name

# Routine Table #

Routing tables are **all** routes the router know to a partucular destination.

## FIB Table ##

This is the calculated forwarding table, configued in the kernel for forwaring
logic.


# Install Dependencies on Debian #

```
sudo aptitude install python3-cairo-dev python3-pil
```
