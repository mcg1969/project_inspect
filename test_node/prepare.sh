#!/bin/bash
for user in *; do
  if [[ -d "$user" ]]; then
    echo "User: $user"
    pushd "$user" >/dev/null
    for project in *; do
      if [[ -d "$project" ]]; then
        echo "  Project: $project"
        pushd "$project" >/dev/null
        if compgen -G "*.yml" >/dev/null; then
          for env in *.yml; do
            echo "    Environment: ${env%.yml}"
            prefix=envs/${env%.yml}
            if [[ ! -d $prefix ]]; then
              conda env create -q -f $env -p $prefix 2>&1 | sed 's@^@      @'
            else
              echo "      environment already exists"
            fi
          done
        fi
        if [[ -f prepare.sh ]]; then
          echo "  Running $user/$project/prepare.sh"
          bash prepare.sh </dev/null
        fi
        popd >/dev/null
      fi
    done
    popd >/dev/null
  fi
done
