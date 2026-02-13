import React, { useState, useEffect, useRef } from 'react'
import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import {
    Activity, Wifi, Cpu, HardDrive, Download, Upload,
    LayoutDashboard, Server, CheckSquare, Settings, User,
    XCircle, RefreshCw, Plus, Trash2, Clock
} from "lucide-react"
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid,
    Tooltip, ResponsiveContainer
} from 'recharts'

export function cn(...inputs) { return twMerge(clsx(inputs)) }

const Button = React.forwardRef(({ className, variant = "default", size = "default", ...props }, ref) => {
    const variants = {
        default: "bg-indigo-600 text-white hover:bg-indigo-700",
        destructive: "bg-red-600 text-white hover:bg-red-700",
        outline: "border border-slate-700 bg-transparent hover:bg-slate-800 text-slate-200",
        secondary: "bg-slate-800 text-slate-200 hover:bg-slate-700",
        ghost: "hover:bg-slate-800 text-slate-400 hover:text-slate-200",
        link: "text-indigo-400 underline-offset-4 hover:underline",
    }
    const sizes = { default: "h-9 px-4 py-2", sm: "h-8 rounded-md px-3 text-xs", lg: "h-10 rounded-md px-8", icon: "h-9 w-9" }
    return (
        <button
            className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500 disabled:pointer-events-none disabled:opacity-50", variants[variant] || variants.default, sizes[size] || sizes.default, className)}
            ref={ref} {...props}
        />
    )
})
Button.displayName = "Button"

const Card = React.forwardRef(({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-xl border border-slate-800/50 bg-slate-900/50 text-slate-50 shadow-sm backdrop-blur-sm", className)} {...props} />
))
Card.displayName = "Card"

const CardHeader = React.forwardRef(({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef(({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("font-semibold leading-none tracking-tight", className)} {...props} />
))
CardTitle.displayName = "CardTitle"

const CardContent = React.forwardRef(({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
))
CardContent.displayName = "CardContent"

const Input = React.forwardRef(({ className, type, ...props }, ref) => (
    <input
        type={type}
        className={cn("flex h-10 w-full rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500 focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 transition-all", className)}
        ref={ref} {...props}
    />
))
Input.displayName = "Input"

function ProcessManager({ processes, onKill }) {
    return (
        <Card className="col-span-4 lg:col-span-2">
            <CardHeader className="flex flex-row items-center justify-between">
                <div><CardTitle>Active Processes</CardTitle><p className="text-sm text-slate-500">Top 20 by CPU usage</p></div>
                <Button variant="outline" size="icon"><RefreshCw className="h-4 w-4" /></Button>
            </CardHeader>
            <CardContent>
                <div className="relative overflow-x-auto">
                    <table className="w-full text-sm text-left text-slate-400">
                        <thead className="text-xs uppercase bg-slate-800/30 text-slate-500">
                            <tr><th className="px-4 py-3">PID</th><th className="px-4 py-3">PROCESS</th><th className="px-4 py-3 text-right">CPU</th><th className="px-4 py-3 text-right">RAM</th><th className="px-4 py-3 text-center">ACTION</th></tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                            {processes?.length > 0 ? (processes.map((proc) => (
                                <tr key={proc.pid} className="hover:bg-slate-800/20 transition-colors">
                                    <td className="px-4 py-2 font-mono text-xs">{proc.pid}</td>
                                    <td className="px-4 py-2 text-slate-200 font-medium truncate max-w-[150px]">{proc.name}</td>
                                    <td className="px-4 py-2 text-right"><span className={cn("px-2 py-0.5 rounded text-[10px]", proc.cpu > 50 ? 'bg-red-500/10 text-red-500' : proc.cpu > 20 ? 'bg-yellow-500/10 text-yellow-500' : 'text-slate-400')}>{proc.cpu}%</span></td>
                                    <td className="px-4 py-2 text-right text-slate-300">{proc.ram}%</td>
                                    <td className="px-4 py-2 text-center"><Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-red-500" onClick={() => onKill(proc.pid)}><XCircle className="h-4 w-4" /></Button></td>
                                </tr>
                            ))) : (<tr><td colSpan="5" className="px-4 py-8 text-center text-slate-600 italic">Waiting for data...</td></tr>)}
                        </tbody>
                    </table>
                </div>
            </CardContent>
        </Card>
    )
}

function ServerMonitor() {
    const [history, setHistory] = useState([])
    const [current, setCurrent] = useState({ cpu: 0, ram: 0, net_rx: 0, net_tx: 0, status: 'offline', processes: [], screenshot: null })
    const socketRef = useRef(null)

    useEffect(() => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsUrl = `${protocol}//${window.location.hostname}:8000/ws/metrics/1`
        const socket = new WebSocket(wsUrl); socketRef.current = socket
        socket.onmessage = (e) => {
            const data = JSON.parse(e.data)
            if (data) {
                setCurrent(prev => ({ ...prev, ...data, screenshot: data.screenshot || prev.screenshot }))
                if (data.time) setHistory(prev => [...prev, { time: data.time, cpu: data.cpu, ram: data.ram }].slice(-20))
            }
        }
        socket.onclose = () => setCurrent(prev => ({ ...prev, status: 'offline' }))
        return () => { if (socketRef.current) socketRef.current.close() }
    }, [])

    const handleKill = (pid) => {
        if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ action: "kill", pid }))
    }

    return (
        <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card><CardHeader className="flex flex-row items-center justify-between pb-2"><CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wider">CPU</CardTitle><Cpu className="h-4 w-4 text-indigo-500" /></CardHeader><CardContent><div className="text-2xl font-bold">{current.cpu}%</div><div className="w-full bg-slate-800 h-1 mt-3 rounded-full overflow-hidden"><div className="bg-indigo-500 h-full transition-all" style={{ width: `${current.cpu}%` }} /></div></CardContent></Card>
                <Card><CardHeader className="flex flex-row items-center justify-between pb-2"><CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wider">RAM</CardTitle><HardDrive className="h-4 w-4 text-blue-500" /></CardHeader><CardContent><div className="text-2xl font-bold">{current.ram}%</div><div className="w-full bg-slate-800 h-1 mt-3 rounded-full overflow-hidden"><div className="bg-blue-500 h-full transition-all" style={{ width: `${current.ram}%` }} /></div></CardContent></Card>
                <Card><CardHeader className="flex flex-row items-center justify-between pb-2"><CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Data</CardTitle><Wifi className="h-4 w-4 text-emerald-500" /></CardHeader><CardContent><div className="flex flex-col text-xs text-slate-300"><div><Download className="h-3 w-3 inline mr-1 text-emerald-500" />{current.net_rx} MB</div><div><Upload className="h-3 w-3 inline mr-1 text-emerald-600" />{current.net_tx} MB</div></div></CardContent></Card>
                <Card><CardHeader className="flex flex-row items-center justify-between pb-2"><CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</CardTitle><Activity className={cn("h-4 w-4", current.status === 'online' ? 'text-green-500 animate-pulse' : 'text-red-500')} /></CardHeader><CardContent><div className={cn("text-2xl font-bold", current.status === 'online' ? 'text-green-500' : 'text-red-500')}>{current.status === 'online' ? 'Stable' : 'Offline'}</div></CardContent></Card>
            </div>
            <div className="grid grid-cols-4 gap-6">
                <Card className="col-span-4 lg:col-span-2"><CardHeader><CardTitle>History</CardTitle></CardHeader><CardContent className="h-[300px] pt-4"><ResponsiveContainer width="100%" height="100%"><LineChart data={history}><XAxis dataKey="time" stroke="#475569" fontSize={10} /><YAxis stroke="#475569" fontSize={10} /><Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b' }} /><CartesianGrid stroke="#1e293b" vertical={false} /><Line type="monotone" dataKey="cpu" stroke="#6366f1" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="ram" stroke="#3b82f6" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></CardContent></Card>
                <Card className="col-span-4 lg:col-span-2 overflow-hidden bg-black/20"><CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-sm font-semibold flex items-center gap-2"><Activity className="h-4 w-4 text-indigo-500" /> Live View</CardTitle><div className="px-2 py-0.5 rounded text-[10px] bg-green-500/10 text-green-500 font-mono">LIVE</div></CardHeader><CardContent className="p-0 border-t border-slate-800/50 relative group bg-black aspect-video flex items-center justify-center">
                    {current.screenshot ? <img src={current.screenshot} alt="VPS" className="w-full h-full object-contain" /> : <div className="text-slate-600 italic">Waiting for feed...</div>}
                </CardContent></Card>
                <ProcessManager processes={current.processes} onKill={handleKill} />
            </div>
        </div>
    )
}

function TaskList() {
    const [tasks, setTasks] = useState([{ id: 1, title: 'Update packages', status: 'todo', priority: 'high' }, { id: 2, title: 'Check logs', status: 'done', priority: 'medium' }])
    const [newTask, setNewTask] = useState('')
    const addTask = (e) => {
        e.preventDefault(); if (!newTask.trim()) return
        setTasks([...tasks, { id: Date.now(), title: newTask, status: 'todo', priority: 'medium' }]); setNewTask('')
    }
    const toggleTask = (id) => setTasks(tasks.map(t => t.id === id ? { ...t, status: t.status === 'done' ? 'todo' : 'done' } : t))
    const deleteTask = (id) => setTasks(tasks.filter(t => t.id !== id))
    const pColor = (p) => p === 'critical' ? 'text-red-500 bg-red-500/10' : p === 'high' ? 'text-orange-500 bg-orange-500/10' : 'text-blue-500 bg-blue-500/10'

    return (
        <Card className="col-span-4 lg:col-span-2 h-full">
            <CardHeader><CardTitle className="flex items-center gap-2"><CheckSquare className="h-5 w-5" /> Quick Tasks</CardTitle></CardHeader>
            <CardContent>
                <form onSubmit={addTask} className="flex gap-2 mb-4"><Input placeholder="Add task..." value={newTask} onChange={(e) => setNewTask(e.target.value)} /><Button type="submit" size="icon"><Plus className="h-4 w-4" /></Button></form>
                <div className="space-y-2">
                    {tasks.map(t => (
                        <div key={t.id} className={cn("flex items-center justify-between p-3 rounded-lg border border-slate-800/50 transition-all", t.status === 'done' ? 'opacity-50 bg-slate-800/30' : 'bg-slate-900/30 hover:bg-slate-800/40')}>
                            <div className="flex items-center gap-3"><Button variant="ghost" size="icon" className={cn("h-6 w-6 rounded border border-slate-700", t.status === 'done' ? 'bg-indigo-600 border-indigo-500 text-white' : '')} onClick={() => toggleTask(t.id)}>{t.status === 'done' && <CheckSquare className="h-4 w-4" />}</Button><div className="flex flex-col"><span className={t.status === 'done' ? 'line-through text-slate-500' : ''}>{t.title}</span><span className={cn("text-[10px] px-1.5 py-0.5 rounded border border-slate-700 w-fit", pColor(t.priority))}>{t.priority.toUpperCase()}</span></div></div>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" onClick={() => deleteTask(t.id)}><Trash2 className="h-4 w-4" /></Button>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    )
}

export default function Nexus() {
    const [activeTab, setActiveTab] = useState('monitoring')

    return (
        <div className="min-h-screen bg-[#020617] text-slate-50 flex font-sans">
            <aside className="w-64 border-r border-slate-800/50 p-6 flex flex-col gap-8 bg-[#020617]/50 backdrop-blur-xl">
                <div className="flex items-center gap-3"><div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-lg text-white">N</div><span className="font-bold text-xl tracking-tight">Nexus<span className="text-indigo-500">Ctrl</span></span></div>
                <nav className="flex-1 flex flex-col gap-2">
                    <button onClick={() => setActiveTab('monitoring')} className={cn("flex items-center gap-3 px-4 py-3 rounded-xl transition-all", activeTab === 'monitoring' ? 'bg-indigo-500/10 text-indigo-400 font-medium border border-indigo-500/20' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50')}><Server className="h-5 w-5" /> Monitoring</button>
                    <button onClick={() => setActiveTab('tasks')} className={cn("flex items-center gap-3 px-4 py-3 rounded-xl transition-all", activeTab === 'tasks' ? 'bg-indigo-500/10 text-indigo-400 font-medium border border-indigo-500/20' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50')}><CheckSquare className="h-5 w-5" /> Task Manager</button>
                </nav>
                <div className="mt-auto border-t border-slate-800/50 pt-6 flex items-center gap-3 px-2"><div className="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400"><User className="h-6 w-6" /></div><div className="flex flex-col"><span className="text-sm font-medium">Administrator</span><span className="text-[10px] text-slate-500 uppercase tracking-widest">Root</span></div></div>
            </aside>
            <main className="flex-1 p-8 overflow-y-auto">
                <header className="flex items-center justify-between mb-8"><div><h1 className="text-3xl font-bold tracking-tight">{activeTab === 'monitoring' ? 'Intelligence' : 'Mission Control'}</h1><p className="text-slate-500 mt-1">{activeTab === 'monitoring' ? 'Real-time performance' : 'Manage your system goals'}</p></div><div className="px-3 py-1.5 rounded-full bg-slate-800/50 border border-slate-700 text-[10px] text-slate-400 flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full bg-green-500" /> SYSTEM ARMED</div></header>
                <div className="animate-in fade-in duration-700">{activeTab === 'monitoring' ? <ServerMonitor /> : <TaskList />}</div>
            </main>
        </div>
    )
}
