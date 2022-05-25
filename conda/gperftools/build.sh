#!/bin/bash

set -ex

# Get an updated config.sub and config.guess
cp $BUILD_PREFIX/share/gnuconfig/config.* .
export CC=$(mpicc -show | cut -d\  -f1) CXX=$(mpicxx -show | cut -d\  -f1)
if [ `uname` == "Darwin" ]; then
    ./configure --prefix $PREFIX --enable-frame-pointers
else
    ./configure --prefix $PREFIX --enable-libunwind --enable-frame-pointers
fi
CORES=${MOOSE_JOBS:-2}
make -j $CORES
make install
# Remove unwanted pprof
mv $(which pprof) $(dirname $(which pprof))/original_pprof
# Build/Install pprof from google
export CC=$(mpicc -show | cut -d\  -f1)
export CXX=$(mpicxx -show | cut -d\  -f1)
export GOPATH="$PREFIX/pprof"
go install github.com/google/pprof@latest
