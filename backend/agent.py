import asyncio
import json
import psutil
import websockets
import base64
import io
from PIL import ImageGrab
from datetime import datetime

BACKEND_URL = "ws://127.0.0.1:8000/ws/agent/1"
AGENT_SECRET = "dev-secret-key-change-me"
UPDATE_INTERVAL = 3

async def get_processes():
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
        try:
            pinfo = proc.info
            procs.append({
                "pid": pinfo['pid'],
                "name": pinfo['name'],
                "user": pinfo['username'],
                "cpu": round(pinfo['cpu_percent'], 1),
                "ram": round(pinfo['memory_percent'], 1)
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    # Sort by CPU and take top 20
    return sorted(procs, key=lambda x: x['cpu'], reverse=True)[:20]

async def capture_screen():
    try:
        img = ImageGrab.grab()
        img.thumbnail((1280, 720))
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=70)
        
        # Base64 encode
        img_str = base64.b64encode(buffer.getvalue()).decode()
        return {"data": f"data:image/jpeg;base64,{img_str}", "status": "ok"}
    except Exception as e:
        emsg = str(e).lower()
        if "screen grab failed" in emsg or "handle" in emsg:
             return {"data": None, "status": "locked", "error": "RDP Session Disconnected (Desktop Locked)"}
        print(f"⚠️ Screenshot failed: {e}")
        return {"data": None, "status": "error", "error": str(e)}

async def collect_metrics(include_screenshot=False):
    cpu = psutil.cpu_percent(interval=None) 
    ram = psutil.virtual_memory().percent
    
    net_stats = psutil.net_io_counters()
    rx_total = round(net_stats.bytes_recv / 1024 / 1024, 2)
    tx_total = round(net_stats.bytes_sent / 1024 / 1024, 2)
    
    processes = await get_processes()
    
    metrics = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "cpu": cpu,
        "ram": ram,
        "net_rx": rx_total,
        "net_tx": tx_total,
        "processes": processes,
        "status": "online",
        "timestamp": datetime.now().isoformat()
    }
    
    if include_screenshot:
        ss_result = await capture_screen()
        metrics["screenshot"] = ss_result["data"]
        metrics["screenshot_status"] = ss_result["status"]
        metrics["screenshot_error"] = ss_result.get("error")
        
    return metrics

async def handle_commands(websocket):
    try:
        async for message in websocket:
            try:
                command = json.loads(message)
                action = command.get("action")
                
                if action == "kill":
                    pid = command.get("pid")
                    if pid:
                        print(f"🔪 Command received: Kill process {pid}")
                        p = psutil.Process(pid)
                        p.terminate()
                        print(f"✅ Process {pid} terminated")
                
            except Exception as e:
                print(f"⚠️ Failed to execute command: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass

async def run_agent():
    print(f"🚀 NexusCtrl Monitoring Agent starting...")
    print(f"🔗 Connecting to {BACKEND_URL}...")
    
    while True:
        try:
            async with websockets.connect(BACKEND_URL) as websocket:
                print("✅ Connected to backend")
                
                # 1. Authenticate with backend
                auth_payload = {"secret": AGENT_SECRET}
                await websocket.send(json.dumps(auth_payload))
                
                # 2. Handle commands asynchronously
                command_task = asyncio.create_task(handle_commands(websocket))
                
                try:
                    counter = 0
                    while True:
                        take_ss = (counter % 5 == 0)
                        metrics = await collect_metrics(include_screenshot=take_ss)
                        await websocket.send(json.dumps(metrics))
                        print(f"📊 Metrics sent. Screenshot: {take_ss}")
                        
                        counter += 1
                        await asyncio.sleep(UPDATE_INTERVAL)
                finally:
                    command_task.cancel()
                    try:
                        await command_task
                    except asyncio.CancelledError:
                        pass
                    
        except Exception as e:
            print(f"❌ Connection error: {e}. Retrying in 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        psutil.cpu_percent(interval=1)
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\n🛑 Agent stopped")
