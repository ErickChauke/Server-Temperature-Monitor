#!/bin/bash

SCC_FILE=/tmp/scc.csv
OK_TEMP=26
WARN_TEMP=28
CRITICAL_TEMP=32
OK_CODE=0
WARN_CODE=1
CRIT_CODE=2
UNKN_CODE=3

wget http://enzweb/data/scc.csv -O $SCC_FILE

line=`tail -n 1 $SCC_FILE`
IFS=',' read -ra array <<< "$line"
#Remove the date
unset 'array[0]'

#Sort
new_array=($(echo "${array[@]}" | sed 's/ /\n/g' | sort))
#
##Remove the highest value
unset 'new_array[3]'
#
##Array length
len=${#new_array[@]}
#
sum=0
for (( i=0; i<$len; i++ )); do sum=$sum+${new_array[i]} ; done

DUVHA_TEMP=`echo "scale=1; ($sum)/$len" | bc -l`
DUVHA_TIME=`tail -n 1 $SCC_FILE | awk -v FS=, '{print $1}'`
if (( $(echo "$DUVHA_TEMP <= $OK_TEMP" |bc -l) )); then
    echo "OK - $DUVHA_TIME: Temperature is normal ($DUVHA_TEMP°C)"
    exit $OK_CODE
elif (( $(echo "$DUVHA_TEMP > $OK_TEMP && $DUVHA_TEMP <= $WARN_TEMP" |bc -l) )); then
    echo "WARNING - $DUVHA_TIME: Temperature acceptable ($DUVHA_TEMP°C)"
    exit $WARN_CODE
elif (( $(echo "$DUVHA_TEMP > $WARN_TEMP" |bc -l) )); then
    echo "CRITICAL - $DUVHA_TIME: Temperature too high ($DUVHA_TEMP°C)"
    exit $CRIT_CODE
else
    echo "INFORMATION - $DUVHA_TIME: Connection is not available"
    exit $UNKN_CODE
fi
