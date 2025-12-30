import asyncio
import logging
from p2p_node import P2PNode

# Setup rudimentary logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

async def robust_test_scenario(algo_name):
    print(f"\n--- Testing Algorithm: {algo_name} ---")
    
    # 1. Broadcaster (Splitter)
    # Role=broadcaster always uses SplitterAlgorithm
    broadcaster = P2PNode(host="127.0.0.1", port=9000, role="broadcaster")
    
    # 2. Viewers using target algo
    viewer1 = P2PNode(host="127.0.0.1", port=9001, role="viewer", algo_name=algo_name)
    viewer2 = P2PNode(host="127.0.0.1", port=9002, role="viewer", algo_name=algo_name)
    
    await broadcaster.start()
    await viewer1.start()
    await viewer2.start()
    
    # Connect Topology: B -> V1, B -> V2, V1 <-> V2
    # Bootstrap connections
    viewer1.connect_to("127.0.0.1", 9000)
    viewer2.connect_to("127.0.0.1", 9000)
    
    # Also connect V1 and V2 to each other manually for test speed
    # (In real run PEX would do this eventually)
    viewer1.connect_to("127.0.0.1", 9002)
    viewer2.connect_to("127.0.0.1", 9001)

    # Allow connection stabilization
    await asyncio.sleep(1)
    
    # 3. Simulate Data Generation (Splitter)
    # Generate 10 chunks.
    # Splitter should RR these. V1 gets 1,3,5.. V2 gets 2,4,6..
    # Then default push (flooding) should propagate them V1->V2 and V2->V1.
    print("Generating 10 data chunks...")
    for seq in range(1, 11):
        payload = f"Payload-{seq}".encode()
        # Mocking logic from main.py broadcaster_loop
        broadcaster.data_store[seq] = payload
        broadcaster.my_bitmap.add(seq)
        broadcaster.algorithm.on_chunk_generated(seq, payload)
        await asyncio.sleep(0.1)
        
    # 4. Wait for propagation
    print("Waiting for P2P propagation...")
    await asyncio.sleep(5.0) # Give enough time for re-broadcast
    
    # 5. Verify
    print(f"Broadcaster Bitmap: {len(broadcaster.my_bitmap)}")
    print(f"Viewer1     Bitmap: {len(viewer1.my_bitmap)}")
    print(f"Viewer2     Bitmap: {len(viewer2.my_bitmap)}")
    
    missing_v1 = 10 - len(viewer1.my_bitmap)
    missing_v2 = 10 - len(viewer2.my_bitmap)
    
    if missing_v1 == 0 and missing_v2 == 0:
        print("SUCCESS: All chunks propagated!")
    else:
        print(f"FAILURE: V1 missing {missing_v1}, V2 missing {missing_v2}")
    
    # Cleanup
    await broadcaster.stop()
    await viewer1.stop()
    await viewer2.stop()

if __name__ == "__main__":
    import sys
    algo = sys.argv[1] if len(sys.argv) > 1 else "default"
    asyncio.run(robust_test_scenario(algo))
