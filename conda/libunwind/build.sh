#!/bin/bash

set -x

autoreconf -fiv

export CC=$(mpicc -show | cut -d\  -f1)
export CXX=$(mpicxx -show | cut -d\  -f1)

./configure --prefix=$PREFIX --disable-static

CORES=${MOOSE_JOBS:-2}
make -j${CORES}
make install

# The tests are known to be flakey so disable them
# make check || true
