import time

from brains_v2.voice_v2.listener import listener

start = time.time()

print(listener.listen())

print()

print(

    "Seconds :",

    round(

        time.time()-start,

        2

    )

)