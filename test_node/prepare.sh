#!/bin/bash
for user in *; do
   if [[ -d "$user" ]]; then
     pushd "$user" >/dev/null
     for project in *; do
     	if [[ -d "$project" ]]; then
          pushd "$project" >/dev/null
          if [[ ! -d envs && -e prepare.sh ]]; then
          	echo "Preparing: $user/$project"
          	mkdir envs
            bash prepare.sh </dev/null
          else
          	echo "Already prepared: $user/$project"
          fi
          popd >/dev/null
        fi
     done
     popd >/dev/null
   fi
done

