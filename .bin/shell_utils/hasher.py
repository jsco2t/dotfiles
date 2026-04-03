#!/usr/bin/env python3
import sys
import hashlib

hash_result = hashlib.sha512(sys.argv[1].encode("utf8")).hexdigest()
print(hash_result)

