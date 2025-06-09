import asyncio
import websockets
import socket
import struct
import uuid
import base64
from urllib.parse import quote
from aiohttp import web, WSMsgType
import aiohttp_cors
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVER = 'bexnxx.nyc.mn'

def generate_uuid():
    """生成随机UUID"""
    return str(uuid.uuid4())

class VLESSProxy:
    def __init__(self, port=8080, uuid_str=None, path="/"):
        self.port = port
        self.uuid = uuid_str or generate_uuid()
        self.path = path
        
    async def handle_http_request(self, request):
        """处理HTTP请求，重定向到指定网站"""
        return web.HTTPFound('https://newsnow.busiyi.world/')
    
    async def handle_websocket(self, request):
        """处理WebSocket连接"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        try:
            # 等待第一条消息
            msg = await ws.receive()
            if msg.type != WSMsgType.BINARY:
                await ws.close()
                return ws
                
            data = msg.data
            if len(data) < 19:
                await ws.close()
                return ws
                
            # 解析VLESS协议头
            version = data[0]
            client_id = data[1:17].hex()
            
            # 验证UUID（如果配置了的话）
            if self.uuid and client_id != self.uuid.replace('-', ''):
                await ws.close()
                return ws
                
            # 解析地址信息
            offset = data[17] + 19
            if offset + 2 > len(data):
                await ws.close()
                return ws
                
            target_port = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            
            if offset >= len(data):
                await ws.close()
                return ws
                
            address_type = data[offset]
            offset += 1
            
            # 解析目标地址
            target_host = self.parse_address(data, offset, address_type)
            if not target_host:
                await ws.close()
                return ws
                
            # 计算剩余数据的起始位置
            if address_type == 1:  # IPv4
                offset += 4
            elif address_type == 2:  # 域名
                domain_len = data[offset] if offset < len(data) else 0
                offset += 1 + domain_len
            elif address_type == 3:  # IPv6
                offset += 16
            
            # 发送响应
            response = bytes([version, 0])
            await ws.send_bytes(response)
            
            # 建立到目标服务器的连接并开始代理
            await self.proxy_connection(ws, target_host, target_port, data[offset:])
            
        except Exception as e:
            logger.error(f"WebSocket处理错误: {e}")
        finally:
            if not ws.closed:
                await ws.close()
                
        return ws
    
    def parse_address(self, data, offset, address_type):
        """解析目标地址"""
        try:
            if address_type == 1:  # IPv4
                if offset + 4 > len(data):
                    return None
                return '.'.join(str(b) for b in data[offset:offset+4])
            elif address_type == 2:  # 域名
                if offset >= len(data):
                    return None
                domain_len = data[offset]
                if offset + 1 + domain_len > len(data):
                    return None
                return data[offset+1:offset+1+domain_len].decode('utf-8')
            elif address_type == 3:  # IPv6
                if offset + 16 > len(data):
                    return None
                ipv6_bytes = data[offset:offset+16]
                # 简化的IPv6格式化
                parts = []
                for i in range(0, 16, 2):
                    part = struct.unpack('>H', ipv6_bytes[i:i+2])[0]
                    parts.append(f'{part:x}')
                return ':'.join(parts)
        except Exception as e:
            logger.error(f"地址解析错误: {e}")
            return None
    
    async def proxy_connection(self, ws, target_host, target_port, initial_data):
        """代理WebSocket和目标服务器之间的连接"""
        try:
            # 连接到目标服务器
            reader, writer = await asyncio.open_connection(target_host, target_port)
            
            # 发送初始数据
            if initial_data:
                writer.write(initial_data)
                await writer.drain()
            
            # 创建双向代理任务
            ws_to_server = asyncio.create_task(
                self.forward_ws_to_server(ws, writer)
            )
            server_to_ws = asyncio.create_task(
                self.forward_server_to_ws(reader, ws)
            )
            
            # 等待任意一个方向的连接关闭
            done, pending = await asyncio.wait(
                [ws_to_server, server_to_ws], 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
                
            writer.close()
            await writer.wait_closed()
            
        except Exception as e:
            logger.error(f"代理连接错误: {e}")
    
    async def forward_ws_to_server(self, ws, writer):
        """从WebSocket转发数据到服务器"""
        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    writer.write(msg.data)
                    await writer.drain()
                elif msg.type == WSMsgType.ERROR:
                    break
        except Exception as e:
            logger.error(f"WebSocket到服务器转发错误: {e}")
    
    async def forward_server_to_ws(self, reader, ws):
        """从服务器转发数据到WebSocket"""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                if ws.closed:
                    break
                await ws.send_bytes(data)
        except Exception as e:
            logger.error(f"服务器到WebSocket转发错误: {e}")
    
    async def start_server(self):
        """启动服务器"""
        app = web.Application()
        
        # 设置CORS
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # 路由设置
        app.router.add_get(self.path, self.handle_websocket)
        app.router.add_get('/{path:.*}', self.handle_http_request)
        
        # 添加CORS到所有路由
        for route in list(app.router.routes()):
            cors.add(route)
        
        # 启动服务器
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', self.port)
        await site.start()
        
        logger.info(f"服务器运行在 http://localhost:{self.port}")
        return runner

async def main():
    """主函数"""
    config = {
        'port': 8080,
        'uuid': 'f65c45c4-08c0-49f4-a2bf-aed46e0c008a',
        'path': '/'
    }
    
    proxy = VLESSProxy(
        port=config['port'],
        uuid_str=config['uuid'],
        path=config['path']
    )
    
    runner = await proxy.start_server()
    
    try:
        # 保持服务器运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("正在关闭服务器...")
    finally:
        await runner.cleanup()

if __name__ == '__main__':
    # 设置异常处理
    def handle_exception(loop, context):
        logger.error(f"未捕获的异常: {context}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(handle_exception)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("程序已退出")
    finally:
        loop.close()
