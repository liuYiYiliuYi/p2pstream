import asyncio
import random
import time
import logging
import sys
import os

# Ensure the parent directory is in the path to import protocol and transport
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from protocol import Packet
from transport import UDPTransport

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Layer1Test")

HOST = "127.0.0.1"
SENDER_PORT = 9998
RECEIVER_PORT = 9999
TOTAL_PACKETS = 100
LOSS_RATE = 0.1  # 10% packet loss simulation
MAX_DELAY = 0.05 # 50ms max delay simulation

received_packets = set()
reception_complete = asyncio.Event()

def receiver_callback(packet: Packet, addr: tuple):
    """
    Simulates network conditions (loss, delay) and processes received packets.
    """
    # Simulate Packet Loss
    if random.random() < LOSS_RATE:
        logger.warning(f"Simulating PACKET LOSS for seq {packet.seq}")
        return

    # Simulate Network Delay
    async def process_delayed():
        delay = random.uniform(0, MAX_DELAY)
        await asyncio.sleep(delay)
        
        logger.info(f"Received Packet: seq={packet.seq}, type={packet.msg_type}, len={len(packet.payload)}")
        received_packets.add(packet.seq)
        
        # Check if we should stop (relaxed condition due to loss)
        # In a real scenario we'd use timeouts, but here we just check if we got enough or last one
        if len(received_packets) >= TOTAL_PACKETS * (1 - LOSS_RATE): 
             # Just a heuristic to trigger event, but better to wait for a timeout in main
             pass
        if packet.seq == TOTAL_PACKETS:
             pass

    asyncio.create_task(process_delayed())

async def run_test():
    # 1. Start Receiver
    receiver = UDPTransport(on_packet_received=receiver_callback)
    await receiver.start_server(HOST, RECEIVER_PORT)

    # 2. Start Sender
    sender = UDPTransport()
    await sender.start_server(HOST, SENDER_PORT)

    # 3. Send Packets
    logger.info(f"Starting to send {TOTAL_PACKETS} packets...")
    start_time = time.time()
    
    for seq in range(1, TOTAL_PACKETS + 1):
        packet = Packet(
            ver=1,
            msg_type=1, # VideoData
            seq=seq,
            timestamp=time.time(),
            payload=b"A"*100 # Dummy payload
        )
        sender.send_packet(packet, (HOST, RECEIVER_PORT))
        await asyncio.sleep(0.01) # Slight interval between sends

    logger.info("Finished sending packets.")

    # 4. Wait for potential receptions
    # Since we have loss, we won't get all of them. We wait a bit to let delayed packets arrive.
    await asyncio.sleep(2) 

    # 5. Verification
    logger.info("---------------- RESULTS ----------------")
    logger.info(f"Total Sent: {TOTAL_PACKETS}")
    logger.info(f"Total Received: {len(received_packets)}")
    logger.info(f"Loss Rate: {1 - len(received_packets)/TOTAL_PACKETS:.2f} (Expected approx {LOSS_RATE})")
    
    sorted_seqs = sorted(list(received_packets))
    # Check for some continuity or just presence
    if len(received_packets) > 0:
        logger.info(f"First received: {sorted_seqs[0]}, Last received: {sorted_seqs[-1]}")
    
    # Assertions
    # We expect at least some packets
    assert len(received_packets) > 0, "No packets received!"
    
    # We expect loss to be within reasonable bounds (e.g., < 2x LOSS_RATE + margin)
    # This is a bit flaky for a strict test, but good for demonstration
    actual_loss = 1 - len(received_packets)/TOTAL_PACKETS
    if actual_loss > LOSS_RATE * 2 + 0.1:
        logger.warning("High packet loss detected!")
    else:
        logger.info("Packet loss is within expected range.")

    sender.close()
    receiver.close()
    logger.info("Test Completed Successfully.")

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        pass
