pdir=$(uname | tr '[:upper:]' '[:lower:]')
for projectgrp in all node owner project environment; do
   for packagegrp in all package version; do
       fname="$pdir/${projectgrp}_${packagegrp}.csv"
       arg="${projectgrp}/${packagegrp}"
       python -m project_inspect --summarize $arg --output $fname --root ../test_node
   done
done
