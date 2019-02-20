#!/bin/bash
for user in *; do
  if [[ -d "$user" ]]; then
    pushd "$user" >/dev/null
    for project in *; do
      if [[ -d "$project" ]]; then
        pushd "$project" >/dev/null
        for env in *.yml; do
          prefix=envs/${env%.yml}
          if [[ -d $prefix ]]; then
            echo "Environment $user/$project/envs/$prefix" already exists
          elif [[ $env != *.yml ]]; then
            echo "Creating $user/$project/envs/$prefix"
            conda env create -f $env -p $prefix
          fi
        done
        if [[ -f prepare.sh ]]; then
          echo "Running $user/$project/prepare.sh"
          bash prepare.sh </dev/null
        fi
        popd >/dev/null
      fi
    done
    popd >/dev/null
  fi
done
