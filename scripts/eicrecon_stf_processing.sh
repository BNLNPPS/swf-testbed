#!/bin/bash
echo 'dummy payload' > myout.txt

# A wrapper that blocks propagation of $@, $1, etc.: sourcing inside the
# function scope after `shift` leaves the sourced script with no positional
# parameters (thisepic.sh would otherwise set DETECTOR_CONFIG=${1:-epic} to
# the input filename this payload was called with).
_sourceWithoutArgs() {
    local fileToSource="$1"
    shift
    . "$fileToSource"
}

eic-info
ls -R
_sourceWithoutArgs /opt/detector/epic-26.03.0/bin/thisepic.sh
IFS="," read -ra FILES <<< "$1"
for infile in "${FILES[@]}"; do
    # inputs are symlinked into /output by the submitter; use the absolute
    # in-container path
    infile="/output/$(basename "$infile")"
    outfile="${infile/.edm4hep.root/.edm4eic.root}"
    eicrecon "$infile" -Ppodio:output_file="$outfile"
done
ls -R
