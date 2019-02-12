# project_inspect

This package implements a variety of tools to inspect and manage
projects stored in the formats supported by Anaconda Project as
well as Anaconda Project 4 and 5. Its primary purpose is to parse
the project's notebooks and source code to determine what packages
are actively imported and to merge that with knowledge from conda
about package dependencies. This information serves a variety of
use cases; the two we are focused on initially include:

- Providing an inventory of package usage on AE4, to determine
  the potential consequences of modifying users' package
  environments; e.g., in response to mandatory package removals
  or upgrades for security purposes.
- To provide an automated approach to converstion of AE4 projects
  to AE5, in a manner that attempts to preserve functionality
  while eliminating unnecessary packages and version pinning from
  the converted project, to maximize portability.

