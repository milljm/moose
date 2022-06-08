#!/bin/bash

set -ex

# Get an updated config.sub and config.guess
cp $BUILD_PREFIX/share/gnuconfig/config.* .
export CC=$(mpicc -show | cut -d\  -f1)
export CXX=$(mpicxx -show | cut -d\  -f1)
unset FC F90 F77
if [ `uname` == "Darwin" ]; then
    ./configure --prefix $PREFIX/gperftools --enable-frame-pointers
else
    LIBRARY_PATH="${PREFIX}/lib:$LIBRARY_PATH" LD_LIBRARY_PATH="${PREFIX}/lib:$LD_LIBRARY_PATH" CPATH="${PREFIX}/include" CPPFLAGS="-I${PREFIX}/include" CFLAGS="-I${PREFIX}/include" LDFLAGS="-L${PREFIX}/lib" ./configure --prefix $PREFIX/gperftools --enable-libunwind --enable-frame-pointers
fi
CORES=${MOOSE_JOBS:-2}
make -j $CORES
make install
# Remove unwanted pprof
export GOPATH="$PREFIX/gperftools"
mv $GOPATH/bin/pprof $GOPATH/bin/original_pprof
# Build/Install pprof from google
# go install github.com/google/pprof@latest
go get -u github.com/google/pprof
ldd $GOPATH/bin/pprof
$GOPATH/bin/pprof -h

# Set PATHs
mkdir -p "${PREFIX}/etc/conda/activate.d" "${PREFIX}/etc/conda/deactivate.d"
cat <<EOF > "${PREFIX}/etc/conda/activate.d/activate_${PKG_NAME}.sh"
export GPERF_OLDPATH=\$PATH
export PATH=${PREFIX}/gperftools/bin:\$PATH
EOF
cat <<EOF > "${PREFIX}/etc/conda/deactivate.d/deactivate_${PKG_NAME}.sh"
export PATH=\$GPERF_OLDPATH
unset GPERF_OLDPATH
EOF
