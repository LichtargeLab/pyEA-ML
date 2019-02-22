#!/usr/bin/env bash

### Environment Setup ###
# readlink -f doesn't work on OS X, so this can only be done on a Linux system
# Alternatively, this will work on OS X if `greadlink` is installed through
# Homebrew and added to PATH
repSource=$(readlink -f `dirname ${BASH_SOURCE[0]}`)
# check for conda
if ! which conda > /dev/null; then
    echo -e "Conda not found! Install? (y/n) \c"
    read REPLY
    if [ "$REPLY" = "y" ]; then
        echo 'export PATH=/lab/cedar/shared/anaconda3/bin:$PATH' >> $HOME/.bashrc
        export PATH='/lab/cedar/shared/anaconda3/bin:$PATH'
    else
        echo "Conda is required for proper virtual environment setup."
        exit 1
    fi
fi

# Set-up the Environment
ENV_NAME='pyEA-ML'

ENVS=$(conda env list | awk '{print $1}' )
if [[ $ENVS = *$ENV_NAME* ]]; then
   source activate ${ENV_NAME}
else
    # make virtual environment
    conda env create -f ${repSource}/environment.yml
    source activate ${ENV_NAME}
fi

# Set-up .env
if [ ! -f ./.env ]; then
    # Make the file
    # Record the results folder destination
    while getopts ":he:d:s:g:" opt; do
        case ${opt} in
            h)
                echo "Usage:"
                echo "./run.sh -e <experiment folder> -d <data> -s <sample file> -g <gene list>"
                echo "./run.sh -h           Display this help message."
                exit 0;;
            e) EXPDIR=$OPTARG;;
            d) DATA=$OPTARG;;
            s) SAMPLES=$OPTARG;;
            g) GENELIST=$OPTARG;;
            \?)
                echo "Invalid Option: -$OPTARG" 1>&2
                exit 1;;
        esac
    done
    shift $((OPTIND -1))
    cd ${EXPDIR}
    touch .env
    dotenv -f .env set EXPDIR $OPTARG
    dotenv -f .env set DATA $OPTARG
    dotenv -f .env set SAMPLES $OPTARG
    dotenv -f .env set GENELIST $OPTARG
fi

# run pipeline
python ${repSource}/src/main.py
