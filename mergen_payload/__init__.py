"""Files mergen runs but does not import.

The CLI shells out to the verification scripts and reads the shipped JSON
schemas and command templates. In a checkout those live beside mergen_cli.py;
in an installed wheel they have to travel with it, so they are mapped into
this package and located through importlib.resources. Nothing here is meant
to be imported: treat it as a directory, not a module.
"""
