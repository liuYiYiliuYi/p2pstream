import asyncio
import logging
import sys
import os

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p2p_node import P2PNode

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')

HOST = "127.0.0.1"
PORT_A = 10001
PORT_B = 10002
PORT_C = 10003

async def run_simulation():
    # 1. Setup Nodes
    # Node A is the broadcaster, has chunks 1, 2, 3
    node_a = P2PNode(HOST, PORT_A, initial_chunks={1, 2, 3})
    # Node B and C are empty viewers
    node_b = P2PNode(HOST, PORT_B, initial_chunks=set())
    node_c = P2PNode(HOST, PORT_C, initial_chunks=set())

    # 2. Start all nodes
    await node_a.start()
    await node_b.start()
    await node_c.start()

    # 3. Bootstrap Connections (Simulate Discovery)
    # B connects to A
    node_b.connect_to(HOST, PORT_A)
    # C connects to A
    node_c.connect_to(HOST, PORT_A)
    
    # Not necessarily connecting B and C directly yet, 
    # but A might share peer lists later (Mesh building - not implemented yet).
    # For now, let's see if B and C can pull from A.

    print("\n--- Simulation Started ---\n")
    print("Node A has: {1, 2, 3}")
    print("Node B has: {}")
    print("Node C has: {}")
    
    # 4. Run for 5 seconds
    for i in range(5):
        await asyncio.sleep(1)
        print(f"Time {i+1}s:")
        print(f"  Node B Bitmap: {node_b.my_bitmap}")
        print(f"  Node C Bitmap: {node_c.my_bitmap}")
        
        # Check if complete
        target = {1, 2, 3}
        if node_b.my_bitmap.issuperset(target) and node_c.my_bitmap.issuperset(target):
            print("\n--- SUCCESS: All nodes synchronized! ---\n")
            break
            
    # 5. Assertions
    assert node_b.my_bitmap.issuperset({1, 2, 3}), f"Node B Failed! Got {node_b.my_bitmap}"
    assert node_c.my_bitmap.issuperset({1, 2, 3}), f"Node C Failed! Got {node_c.my_bitmap}"

    # 6. Cleanup
    await node_a.stop()
    await node_b.stop()
    await node_c.stop()
    print("Test Completed.")

if __name__ == "__main__":
    try:
        asyncio.run(run_simulation())
    except KeyboardInterrupt:
        pass
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        exit(1)
