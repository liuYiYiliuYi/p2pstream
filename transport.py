import asyncio
import logging
from typing import Callable, Optional
from protocol import Packet

logger = logging.getLogger(__name__)

class UDPTransport:
    def __init__(self, on_packet_received: Optional[Callable[[Packet, tuple], None]] = None):
        """
        :param on_packet_received: Callback function (packet, addr) -> None
        """
        self.transport = None
        self.protocol = None
        self.on_packet_received = on_packet_received

    class _Protocol(asyncio.DatagramProtocol):
        def __init__(self, outer):
            self.outer = outer

        def connection_made(self, transport):
            self.outer.transport = transport
            logger.info("UDP Transport connection made")

        def datagram_received(self, data, addr):
            # Stats integration
            try:
                from stats_manager import StatsManager
                StatsManager().add_download(len(data), f"{addr[0]}:{addr[1]}")
            except ImportError:
                pass
            
            try:
                packet = Packet.unpack(data)
                if self.outer.on_packet_received:
                    self.outer.on_packet_received(packet, addr)
            except Exception as e:
                logger.error(f"Error unpacking packet from {addr}: {e}")

        def error_received(self, exc):
            logger.error(f"UDP Transport error received: {exc}")

        def connection_lost(self, exc):
            logger.info("UDP Transport connection lost")

    async def start_server(self, host: str, port: int):
        """
        Binds the UDP socket to the given host and port.
        """
        loop = asyncio.get_running_loop()
        # Create the datagram endpoint
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: self._Protocol(self),
            local_addr=(host, port)
        )
        self.transport = transport
        self.protocol = protocol
        logger.info(f"UDP Server started on {host}:{port}")

    def send_packet(self, packet: Packet, addr: tuple):
        """
        Serializes and sends a packet to the specified address.
        """
        if self.transport is None:
            logger.warning("Transport is not open. Cannot send packet.")
            return
        
        try:
            data = packet.pack()
            self.transport.sendto(data, addr)
            # Stats integration
            try:
                from stats_manager import StatsManager
                StatsManager().add_upload(len(data))
            except ImportError:
                pass
        except Exception as e:
            logger.error(f"Failed to send packet to {addr}: {e}")

    def close(self):
        """
        Closes the transport.
        """
        if self.transport:
            self.transport.close()
            logger.info("UDP Transport closed")
