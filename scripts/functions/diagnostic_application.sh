#!/bin/bash
#* This file is part of the MOOSE framework
#* https://www.mooseframework.org
#*
#* All rights reserved, see COPYRIGHT for full restrictions
#* https://github.com/idaholab/moose/blob/master/COPYRIGHT
#*
#* Licensed under LGPL 2.1, please see LICENSE for details
#* https://www.gnu.org/licenses/lgpl-2.1.html

function enter_moose()
{
    # TODO: allow a --use-moose-dir argument
    cd $CTMP_DIR/moose || exit_on_failure 1
}

function clone_moose()
{
    # TODO: allow a --use-moose-dir argument
    printf "Cloning MOOSE repository\n\n"
    if [ -z "${retry_cnt}" ]; then
        export retry_cnt=0
    else
        let retry_cnt+=1
    fi
    local COMMAND="git clone --depth 1 https://github.com/idaholab/moose ${CTMP_DIR}/moose -b master"
    if [ "${VERBOSITY}" == 1 ]; then
        set -o pipefail
        run_command "${COMMAND}" 2>&1 | tee ${CTMP_DIR}/moose_clone_stdouterr.log
        local exit_code=$?
        set +o pipefail
    else
        ${COMMAND} &> ${CTMP_DIR}/moose_clone_stdouterr.log
        local exit_code=$?
    fi
    if [ ${exit_code} -ge 1 ] && [ $(cat ${CTMP_DIR}/moose_clone_stdouterr.log | grep -c -i 'SSL') -ge 1 ]; then
        if [ -n "${retry_cnt}" ] && [ ${retry_cnt} -ge 2 ]; then
            print_red "\n${retry_cnt} attempt failure.\n"
            exit_on_failure 1
            clone_moose
            return
        elif [ "${GIT_SSL_NO_VERIFY}" == 'true' ]; then
            print_orange "\n${retry_cnt} attempt failure.\n"
            clone_moose
            return
        fi
        if [ "${VERBOSITY}" == 0 ]; then
            run_command "tail -15 ${CTMP_DIR}/moose_clone_stdouterr.log"
        fi
        print_orange "\nWARNING: "
        printf "SSL issues detected.

This may indicate the root cause of other issues. e.g PETSc contribs may fail to download properly
in later steps.

Trying again with protections turned off...\n"
        print_orange "export GIT_SSL_NO_VERIFY=true\n\n"
        export GIT_SSL_NO_VERIFY=true
        clone_moose
        unset GIT_SSL_NO_VERIFY
        return
    elif [ $(cat ${CTMP_DIR}/moose_clone_stdouterr.log | grep -c -i 'SSL') -ge 1 ]; then
        if [ "${VERBOSITY}" == 0 ]; then
            run_command "tail -15 ${CTMP_DIR}/moose_clone_stdouterr.log"
        fi
        print_orange "\nWARNING: "
        printf "Additional SSL issues detected even after turning GIT SSL verification off. This
indicates a networking issue. Continuing, but it is very likely we will fail if we attempt to
build PETSc.\n\n"
        export ALREADY_TRIED_SSL=true
    elif [ ${exit_code} -ge 1 ]; then
        exit_on_failure 1
    fi
    # Print relevant repo data
    #run_command "git -C ${CTMP_DIR}/moose log -1"
    run_command "git -C ${CTMP_DIR}/moose branch"
    run_command "git -C ${CTMP_DIR}/moose status"
}

function build_library()
{
    if [ "${FULL_BUILD}" == 0 ]; then return; fi
    local error_cnt=${error_cnt:-0}
    if [ ${error_cnt} -le 0 ]; then print_sep; printf "Build Step: $1\n\n"; fi
    enter_moose
    printf "Running scripts/update_and_rebuild_${1}.sh using ${MOOSE_JOBS:-6} jobs, METHODS: ${METHODS}\n"
    if [ "${VERBOSITY}" == 1 ]; then
        set -o pipefail
        run_command "scripts/update_and_rebuild_${1}.sh" 2>&1 | tee ./${1}_stdouterr.log
        exit_code=$?
        set +o pipefail
    else
        scripts/update_and_rebuild_${1}.sh &> ./${1}_stdouterr.log
        exit_code=$?
    fi
    if [ "$exit_code" != '0' ] && [ ${error_cnt} -ge 1 ]; then
        print_failure_and_exit $(tail -20 ./${1}_stdouterr.log)
    elif [ "$exit_code" != '0' ] && [ $(cat ./${1}_stdouterr.log | grep -c -i 'SSL certificate problem') -ge 1 ]; then
        let error_cnt+=1
        if [ "${VERBOSITY}" == 0 ]; then
            run_command "tail -15 ./${1}_stdouterr.log"
        fi
        print_orange "\nWARNING: "
        printf "SSL issues detected, attempting again with SSL protections off\n\n"
        export GIT_SSL_NO_VERIFY=true
        build_library $1
        return
    elif [ "$exit_code" != '0' ]; then
        if [ "${VERBOSITY}" == 0 ]; then
            run_command "tail -15 ${1}_stdouterr.log"
        fi
        print_failure_and_exit "building $1"
    fi
    printf "Successfully built ${1} ...\n"
}

function build_moose()
{
    printf "Build Step: MOOSE. Using ${MOOSE_JOBS:-6} cores\n\n"
    enter_moose
    cd test
    if [ "${VERBOSITY}" == 1 ]; then
        set -o pipefail
        run_command "METHOD=${METHOD} make -j ${MOOSE_JOBS:-6}" 2>&1 | tee ./stdouterr.log
        exit_code=$?
        set +o pipefail
    else
        METHOD=${METHOD} make -j ${MOOSE_JOBS:-6} &> ./stdouterr.log
        exit_code=$?
    fi
    if [ "$exit_code" != '0' ]; then
        if [ "${VERBOSITY}" == 0 ]; then
            tail -20 ./stdouterr.log
        fi
        print_failure_and_exit "building MOOSE"
    fi
    printf "Successfully built MOOSE\n"
}

function build_application()
{
    print_sep
    clone_moose
    # Do the dumb necessary things we do in 'moose-mpich' package
    # TODO: remove this when 'moose-mpi' becomes available
    TEMP_CXXFLAGS=${CXXFLAGS//-std=c++[0-9][0-9]}
    ACTIVATION_CXXFLAGS=${TEMP_CXXFLAGS%%-fdebug-prefix-map*}-std=c++17
    export CC=mpicc CXX=mpicxx FC=mpif90 F90=mpif90 F77=mpif77 C_INCLUDE_PATH=${CONDA_PREFIX}/include MOOSE_NO_CODESIGN=true MPIHOME=${CONDA_PREFIX} CXXFLAGS="$ACTIVATION_CXXFLAGS" HDF5_DIR=${CONDA_PREFIX} FI_PROVIDER=tcp

    local LIBS=(petsc libmesh wasp)
    for lib in ${LIBS[@]}; do
        build_library ${lib}
    done
    print_sep
    build_moose
}
