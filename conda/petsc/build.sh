#!/bin/bash
#
#export PATH=/bin:$PATH
export PETSC_DIR=$SRC_DIR
export PETSC_ARCH=arch-conda-c-opt
#
#export CC=$(basename "$CC")
#export CXX=$(basename "$CXX")
#export FC=$(basename "$FC")
#
## feed-stock recommendation
## scrub debug-prefix-map args, which cause problems in pkg-config
#export CFLAGS=$(echo ${CFLAGS:-} | sed -E 's@\-fdebug\-prefix\-map[^ ]*@@g')
#export CXXFLAGS=$(echo ${CXXFLAGS:-} | sed -E 's@\-fdebug\-prefix\-map[^ ]*@@g')
#export FFLAGS=$(echo ${FFLAGS:-} | sed -E 's@\-fdebug\-prefix\-map[^ ]*@@g')
#export FCFLAGS="$FFLAGS"
#export HYDRA_LAUNCHER=fork
#
#if [[ $(uname) == Darwin ]]; then
#    BUILD_VARIANT=""
#    if [[ $HOST == arm64-apple-darwin20.0.0 ]]; then
#        CFLAGS="${CFLAGS} -mcpu=apple-a12"
#        CXXFLAGS="${CXXFLAGS} -mcpu=apple-a12"
#        FFLAGS="${FFLAGS} -march=armv8.3-a"
#        FCFLAGS="${FCFLAGS} -march=armv8.3-a"
#    else
#        CFLAGS="${CFLAGS} -march=core2 -mtune=haswell"
#        CXXFLAGS="${CXXFLAGS} -march=core2 -mtune=haswell"
#        FFLAGS="${FFLAGS} -I$PREFIX/include"
#        FCFLAGS="${FCFLAGS} -I$PREFIX/include"
#    fi
#else
#    BUILD_VARIANT=${build_variant}
#    CFLAGS="${CFLAGS} -march=nocona -mtune=haswell"
#    CXXFLAGS="${CXXFLAGS} -march=nocona -mtune=haswell"
#    FFLAGS="${FFLAGS} -I$PREFIX/include"
#    FCFLAGS="${FCFLAGS} -I$PREFIX/include"
#fi
#
## Remove std=C++17 from CXXFLAGS as we specify the C++ dialect for PETSc as C++17 in configure_petsc.
## Specifying both causes an error as of PETSc 3.17.
CXXFLAGS=${CXXFLAGS//-std=c++[0-9][0-9]}
#
## Stole this from petsc-feedstock in an attempt to solve the openmpi error:
## mca_base_component_repository_open: unable to open mca_btl_openib: librdmacm.so.1: cannot open shared object file: No such file or directory
#if [[ $mpi == "openmpi" ]]; then
#  export LIBS="-Wl,-rpath,$PREFIX/lib -lmpi_mpifh -lgfortran"
#elif [[ $mpi == "mpich" ]]; then
#  export LIBS="-lmpifort -lgfortran"
#fi
#
## Handle switches created by Conda variants
ADDITIONAL_ARGS=""
#if [[ "${BUILD_VARIANT}" == 'cuda' ]]; then
#  # hacky hack hack
#  cd $BUILD_PREFIX/lib
#  rm -f libnvToolsExt.so
#  ln -s ../targets/x86_64-linux/lib/libnvToolsExt.so.1.0.0 libnvToolsExt.so
#  cd -
#
#  CXXFLAGS+=" -I${PREFIX}/nsight-compute-2024.1.0/host/target-linux-x64/nvtx/include/nvtx3"
#  CFLAGS+=" -I${PREFIX}/nsight-compute-2024.1.0/host/target-linux-x64/nvtx/include/nvtx3"
#  ADDITIONAL_ARGS+=" --download-slate=1 --with-cuda=1 --with-cudac=${PREFIX}/bin/nvcc --with-cuda-dir=${PREFIX}/targets/x86_64-linux --CUDAFLAGS=-I${PREFIX}/targets/x86_64-linux/include"
#fi

source $SRC_DIR/configure_petsc.sh
configure_petsc \
      --COPTFLAGS=-O3 \
      --CXXOPTFLAGS=-O3 \
      --FOPTFLAGS=-O3 \
      --with-x=0 \
      --with-ssl=0 \
      --with-hdf5-dir=$HDF5_DIR \
      --with-mpi-dir=$PREFIX \
      AR="$AR" \
      RANLIB="$RANLIB" \
      CFLAGS="$CFLAGS" \
      CXXFLAGS="$CXXFLAGS" \
      CPPFLAGS="$CPPFLAGS" \
      FFLAGS="$FFLAGS" \
      FCFLAGS="$FFLAGS" \
      LDFLAGS="$LDFLAGS" \
      ${ADDITIONAL_ARGS} \
      --prefix=$PREFIX/petsc || (tail -400 configure.log && exit 1)

## Verify that gcc_ext isn't linked
#for f in $PETSC_ARCH/lib/petsc/conf/petscvariables $PETSC_ARCH/lib/pkgconfig/PETSc.pc; do
#  if grep gcc_ext $f; then
#    echo "gcc_ext found in $f"
#    exit 1
#  fi
#done
#
sedinplace() {
  if [[ $(uname) == Darwin ]]; then
    sed -i "" "$@"
  else
    sed -i"" "$@"
  fi
}
#
## Remove abspath of ${BUILD_PREFIX}/bin/python
#sedinplace "s%${BUILD_PREFIX}/bin/python%python%g" $PETSC_ARCH/include/petscconf.h
#sedinplace "s%${BUILD_PREFIX}/bin/python%python%g" $PETSC_ARCH/lib/petsc/conf/petscvariables
#sedinplace "s%${BUILD_PREFIX}/bin/python%/usr/bin/env python%g" $PETSC_ARCH/lib/petsc/conf/reconfigure-arch-conda-c-opt.py
#
## Replace abspath of ${PETSC_DIR} and ${BUILD_PREFIX} with ${PREFIX}
#for path in $PETSC_DIR $BUILD_PREFIX; do
#    for f in $(grep -l "${path}" $PETSC_ARCH/include/petsc*.h); do
#        echo "Fixing ${path} in $f"
#        sedinplace s%$path%\${PREFIX}/moose-petsc/%g $f
#    done
#done
#
#make
## damn... again I have to disable this. (openmpi strange missing libraries error)
#if [[ $mpi == "mpich" ]] && [[ $(uname) == Linux ]]; then
#  make check
#fi
make PETSC_DIR=$SRC_DIR PETSC_ARCH=$PETSC_ARCH all
make PETSC_DIR=$SRC_DIR PETSC_ARCH=$PETSC_ARCH install

#make SLEPC_DIR=$SRC_DIR/arch-linux-c-opt/externalpackages/git.slepc PETSC_DIR=$PREFIX/moose-petsc install
#make SLEPC_DIR=/data/milljm/civet_testing/moose/petsc/arch-moose/externalpackages/git.slepc PETSC_DIR=/data/milljm/civet_testing/moose/petsc PETSC_ARCH=arch-moose
#
## Remove unneeded files
#rm -f ${PREFIX}/moose-petsc/lib/petsc/conf/configure-hash
#find ${PREFIX}/moose-petsc/lib/petsc -name '*.pyc' -delete
#
## Replace ${BUILD_PREFIX} after installation,
## otherwise 'make install' above may fail
for f in $(grep -l "${BUILD_PREFIX}" -R "${PREFIX}/petsc/lib/petsc"); do
  echo "Fixing ${BUILD_PREFIX} in $f"
  sedinplace s%${BUILD_PREFIX}%${PREFIX}%g $f
done
#
#echo "Removing example files"
#du -hs $PREFIX/moose-petsc/share/petsc/examples/src
#rm -fr $PREFIX/moose-petsc/share/petsc/examples/src
#echo "Removing data files"
#du -hs $PREFIX/moose-petsc/share/petsc/datafiles/*
#rm -fr $PREFIX/moose-petsc/share/petsc/datafiles
#
# Set PETSC_DIR environment variable for those that need it
mkdir -p "${PREFIX}/etc/conda/activate.d" "${PREFIX}/etc/conda/deactivate.d"
cat <<EOF > "${PREFIX}/etc/conda/activate.d/activate_${PKG_NAME}.sh"
export PETSC_DIR=${PREFIX}/petsc
export PKG_CONFIG_PATH=${PREFIX}/petsc/lib/pkgconfig:\${PKG_CONFIG_PATH}
EOF
cat <<EOF > "${PREFIX}/etc/conda/deactivate.d/deactivate_${PKG_NAME}.sh"
unset PETSC_DIR
export PKG_CONFIG_PATH=\${PKG_CONFIG_PATH%":${PREFIX}/petsc/lib/pkgconfig"}
EOF
#
## Cuda specific activation/deactivation variables (append to above created script)
#if [[ "${BUILD_VARIANT}" == 'cuda' ]] && [[ $mpi == "openmpi" ]]; then
#cat <<EOF >> "${PREFIX}/etc/conda/activate.d/activate_${PKG_NAME}.sh"
#export OMPI_MCA_opal_cuda_support=true
#EOF
#cat <<EOF >> "${PREFIX}/etc/conda/deactivate.d/deactivate_${PKG_NAME}.sh"
#unset OMPI_MCA_opal_cuda_support
#EOF
#fi
#