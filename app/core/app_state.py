import time

# Recorded at process import time (before lifespan even runs), used to compute
# process uptime for /v1/stats/summary. Resets on every restart by design.
START_TIME = time.time()
