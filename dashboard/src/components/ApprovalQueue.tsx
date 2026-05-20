"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Rocket,
  RefreshCw,
  MessageSquare,
  ThumbsUp,
  Clock,
  Hash,
  CheckCircle2,
  Sparkles,
  Send,
  Terminal,
  PenTool,
} from "lucide-react";

interface StreamedTask {
  task: string;
  output: string;
}

export default function ApprovalQueue({ 
  onGeneratingChange,
  onTasksUpdate
}: { 
  onGeneratingChange?: (val: boolean) => void;
  onTasksUpdate?: (tasks: StreamedTask[]) => void;
}) {
  const [status, setStatus] = useState<
    "pending" | "approved" | "regenerating" | "idle"
  >("idle");
  const [topic, setTopic] = useState("");
  const [generatedContent, setGeneratedContent] = useState("");
  const [streamedTasks, setStreamedTasks] = useState<StreamedTask[]>([]);
  
  // Image Generation State
  const [imageStatus, setImageStatus] = useState<"idle" | "generating" | "done" | "error">("idle");
  const [generatedImages, setGeneratedImages] = useState<string[]>([]);
  const [palette, setPalette] = useState("void_purple");
  const [layout, setLayout] = useState("bottom_hero");
  const [imageModel, setImageModel] = useState("sdxl_turbo");
  const [imageScene, setImageScene] = useState("");

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    onTasksUpdate?.(streamedTasks);
  }, [streamedTasks, onTasksUpdate]);

  useEffect(() => {
    // Cleanup WebSocket on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const handleApprove = () => {
    setStatus("approved");
    setTimeout(() => setStatus("pending"), 3000);
  };

  const handleRegenerate = (isAuto: boolean = false) => {
    if (!isAuto && !topic) return alert("Please enter a topic first");
    
    // Clear previous state
    setStreamedTasks([]);
    setGeneratedContent("");
    setStatus("regenerating");
    onGeneratingChange?.(true);

    // Generate a pseudo-random client ID for the socket
    const clientId = Math.random().toString(36).substring(7);
    const endpoint = isAuto ? `auto-generate/${clientId}` : `generate/${clientId}`;
    
    // Support both ws:// and wss:// dynamically based on the env string
    const baseUrl = process.env.NEXT_PUBLIC_BACKEND_API || "http://127.0.0.1:8000";
    const wsProtocol = baseUrl.startsWith("https") ? "wss" : "ws";
    const wsHost = baseUrl.replace(/^https?:\/\//, "");
    const wsUrl = `${wsProtocol}://${wsHost}/api/ws/${endpoint}`;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log(`WebSocket connected. Mode: ${isAuto ? "Auto" : "Manual"}`);
      // Send the payload. The auto-generate endpoint ignores the topic field, 
      // but we send it for safety to prevent JSON parse errors.
      ws.send(JSON.stringify({ topic: isAuto ? "auto" : topic, provider: "nvidia" }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("WS Message:", data);

        if (data.type === "task_finished") {
          setStreamedTasks(prev => [...prev, { task: data.task, output: data.output }]);
        } else if (data.type === "complete") {
          setGeneratedContent(data.result);
          setStatus("pending");
          onGeneratingChange?.(false);
          ws.close();
        } else if (data.type === "error") {
          alert(`Generation failed: ${data.message}`);
          setStatus("idle");
          onGeneratingChange?.(false);
          ws.close();
        }
      } catch (err) {
        console.error("Failed to parse WS message", err);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      alert("WebSocket connection failed. Ensure backend is running.");
      setStatus("idle");
      onGeneratingChange?.(false);
    };
  };

  const handleGenerateImage = async () => {
    setImageStatus("generating");
    setGeneratedImages([]);
    
    try {
      const baseUrl = process.env.NEXT_PUBLIC_BACKEND_API || "http://127.0.0.1:8000";
      const res = await fetch(`${baseUrl}/api/instagram/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: imageScene.trim() || topic || "AI Developer Content",
          palette: palette,
          layout: layout,
          model: imageModel,
        })
      });
      
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Error: ${res.statusText}`);
      }
      
      if (data.images && data.images.length > 0) {
        setGeneratedImages(data.images.map((b64: string) => `data:image/png;base64,${b64}`));
        setImageStatus("done");
      } else {
        throw new Error("No images returned. ComfyUI might have failed silently.");
      }
    } catch (err: any) {
      console.error(err);
      alert(`Image generation failed: ${err.message}`);
      setImageStatus("error");
    }
  };

  return (
    <section className="w-full">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="flex items-center gap-2 mb-6">
          <div className="w-1 h-4 bg-gradient-to-b from-purple-500 to-pink-500 rounded-full" />
          <h2 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
            Approval Queue
          </h2>
          <div className="flex items-center gap-2 ml-3">
            <span className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-[9px] font-bold text-amber-400 tracking-wider uppercase">
              {status === "pending" ? "1 Pending Review" : "0 Pending Review"}
            </span>
          </div>
          <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2" />
        </div>

        {/* Topic Input Bar */}
        <div className="mb-6 flex gap-3">
          <div className="flex-1 glass-card rounded-xl px-4 py-2 flex items-center gap-3 border border-white/10 focus-within:border-blue-500/50 transition-colors">
            <MessageSquare className="w-4 h-4 text-slate-500" />
            <input 
              type="text" 
              placeholder="Enter viral topic (e.g. FastAPI vs Django for AI)..."
              className="bg-transparent border-none outline-none text-sm text-white w-full placeholder:text-slate-600"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={status === "regenerating"}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && topic && status !== 'regenerating') {
                  handleRegenerate();
                }
              }}
            />
          </div>
            <div className="flex gap-2">
              <button 
                onClick={() => handleRegenerate(true)}
                disabled={status === "regenerating"}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 disabled:opacity-50 disabled:cursor-not-allowed text-xs font-bold tracking-widest uppercase text-white transition-all shadow-[0_0_15px_rgba(168,85,247,0.3)] hover:shadow-[0_0_20px_rgba(168,85,247,0.5)] flex items-center gap-2 cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Auto-Research Magic
              </button>
              
              <button 
                onClick={() => handleRegenerate(false)}
                disabled={status === "regenerating" || !topic}
                className="px-6 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-xs font-bold tracking-widest uppercase text-white transition-colors flex items-center gap-2 cursor-pointer"
              >
                {status === "regenerating" ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
                {status === "regenerating" ? "Running..." : "Generate"}
              </button>
            </div>
          </div>

        {/* Streaming Task Output */}
        <AnimatePresence>
          {streamedTasks.length > 0 && (status === "regenerating" || status === "pending") && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-8 flex flex-col gap-4"
            >
              {streamedTasks.map((st, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="glass-card p-4 rounded-xl border border-white/5 bg-slate-900/40"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Terminal className="w-4 h-4 text-green-400" />
                    <span className="text-xs font-bold text-green-400 uppercase tracking-wider">
                      {st.task} Completed
                    </span>
                  </div>
                  <div className="text-sm text-slate-300 whitespace-pre-line font-sans max-h-40 overflow-y-auto pr-2 custom-scrollbar">
                    {st.output}
                  </div>
                </motion.div>
              ))}
              
              {status === "regenerating" && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="glass-card p-4 rounded-xl border border-white/5 flex items-center gap-3 animate-pulse"
                >
                  <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
                  <span className="text-xs font-bold text-blue-400 uppercase tracking-wider">
                    Next Agent Thinking...
                  </span>
                </motion.div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Final Review Card */}
        <AnimatePresence mode="wait">
          {(status === "pending" || status === "approved") ? (
            <motion.div
              layout
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              className="glass-card-elevated rounded-2xl overflow-hidden mt-6"
            >
              {/* Card Header */}
              <div className="flex items-center justify-between px-5 sm:px-6 py-4 border-b border-white/5 bg-gradient-to-r from-blue-900/20 to-purple-900/20">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-purple-500/20">
                    <Sparkles className="w-3.5 h-3.5 text-white" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white">
                      Final Production Ready Content
                    </h3>
                    <p className="text-[10px] text-slate-400 tracking-wide uppercase">
                      All Agents Completed Successfully
                    </p>
                  </div>
                </div>
              </div>

              {/* Post Content */}
              <div className="px-5 sm:px-6 py-5">
                <div className="bg-slate-900/80 rounded-xl border border-white/10 p-5 sm:p-6 max-h-96 overflow-y-auto custom-scrollbar shadow-inner">
                  <div className="text-sm text-slate-200 leading-relaxed whitespace-pre-line font-sans flex flex-col gap-2">
                    {generatedContent.split(/(!\[.*?\]\(.*?\))/g).map((part, i) => {
                      const match = part.match(/!\[(.*?)\]\((.*?)\)/);
                      if (match) {
                        return (
                          <div key={i} className="my-4">
                            <img src={match[2]} alt={match[1]} className="rounded-xl max-w-sm w-full border border-white/20 shadow-lg object-contain bg-black/50" />
                          </div>
                        );
                      }
                      return <span key={i}>{part}</span>;
                    })}
                  </div>
                </div>
              </div>

              {/* Instagram Image Generation Section */}
              <div className="px-5 sm:px-6 py-4 border-t border-white/5 bg-slate-900/50">
                <div className="flex items-center gap-2 mb-4">
                  <Terminal className="w-4 h-4 text-purple-400" />
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Independent Image Generation</h4>
                </div>
                
                <div className="mb-4">
                  <label className="block text-[10px] text-slate-500 uppercase tracking-widest mb-1.5 font-semibold">Scene / Subject Description</label>
                  <input 
                    type="text" 
                    placeholder={`e.g. ${topic || 'A futuristic AI glowing core...'}`}
                    className="w-full bg-slate-800 border border-white/10 rounded-lg px-4 py-2 text-sm text-white outline-none focus:border-purple-500/50 transition-colors placeholder:text-slate-600"
                    value={imageScene}
                    onChange={(e) => setImageScene(e.target.value)}
                  />
                  <p className="mt-1 text-[10px] text-slate-500">Leave blank to just use your original topic.</p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase tracking-widest mb-1.5 font-semibold">Palette</label>
                    <select 
                      className="w-full bg-slate-800 border border-white/10 rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-purple-500/50 transition-colors cursor-pointer"
                      value={palette}
                      onChange={(e) => setPalette(e.target.value)}
                    >
                      <option value="void_purple">Void Purple (Cyberpunk)</option>
                      <option value="cyber_teal">Cyber Teal (Bioluminescent)</option>
                      <option value="neon_coral">Neon Coral (Warm Energy)</option>
                      <option value="solar_amber">Solar Amber (Cinematic)</option>
                      <option value="pure_dark">Pure Dark (Monochrome)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase tracking-widest mb-1.5 font-semibold">Layout</label>
                    <select 
                      className="w-full bg-slate-800 border border-white/10 rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-purple-500/50 transition-colors cursor-pointer"
                      value={layout}
                      onChange={(e) => setLayout(e.target.value)}
                    >
                      <option value="bottom_hero">Bottom Hero (For Text)</option>
                      <option value="top_title">Top Title (Center Anchor)</option>
                      <option value="center_bold">Center Bold (Radial)</option>
                      <option value="minimal">Minimal (70% Space)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase tracking-widest mb-1.5 font-semibold">AI Model</label>
                    <select 
                      className="w-full bg-slate-800 border border-white/10 rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-purple-500/50 transition-colors cursor-pointer"
                      value={imageModel}
                      onChange={(e) => setImageModel(e.target.value)}
                    >
                      <option value="sdxl_turbo">SDXL Turbo (Fast ~3s)</option>
                      <option value="flux_schnell">Flux Schnell (High Quality ~8s)</option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-4">
                  <button 
                    onClick={handleGenerateImage}
                    disabled={imageStatus === "generating"}
                    className="w-full sm:w-auto self-start px-6 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 disabled:opacity-50 text-xs font-bold tracking-widest uppercase text-white transition-all shadow-[0_0_15px_rgba(147,51,234,0.3)] flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {imageStatus === "generating" ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <PenTool className="w-4 h-4" />
                    )}
                    {imageStatus === "generating" ? "Instructing ComfyUI..." : "Generate Instagram Image"}
                  </button>

                  {/* Render resulting images */}
                  {generatedImages.length > 0 && (
                    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {generatedImages.map((src, idx) => (
                        <div key={idx} className="relative rounded-xl overflow-hidden border border-white/10 shadow-2xl bg-black/50 aspect-[4/5] max-w-[360px]">
                          <img src={src} alt="Generated UI" className="w-full h-full object-cover" />
                        </div>
                      ))}
                    </motion.div>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="px-5 sm:px-6 pb-5 flex flex-col sm:flex-row gap-3">
                <AnimatePresence mode="wait">
                  {status === "pending" && (
                    <motion.div
                      key="actions"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="flex flex-col sm:flex-row gap-3 w-full"
                    >
                      <motion.button
                        whileHover={{ scale: 1.02, y: -1 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={handleApprove}
                        className="
                          flex-1 flex items-center justify-center gap-3 
                          px-6 py-4 rounded-xl font-bold text-sm tracking-wider uppercase
                          bg-gradient-to-r from-green-600 to-emerald-500
                          text-white
                          shadow-[0_0_20px_rgba(34,197,94,0.3)]
                          hover:shadow-[0_0_30px_rgba(34,197,94,0.5)]
                          transition-shadow duration-300
                          cursor-pointer
                        "
                      >
                        <Rocket className="w-5 h-5" />
                        Approve & Deploy
                      </motion.button>

                      <motion.button
                        whileHover={{ scale: 1.02, y: -1 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => {
                          setStreamedTasks([]);
                          setGeneratedContent("");
                          setStatus("idle");
                        }}
                        className="
                          flex-1 flex items-center justify-center gap-3 
                          px-6 py-4 rounded-xl font-bold text-sm tracking-wider uppercase
                          bg-white/5 hover:bg-white/10
                          text-slate-300
                          border border-white/10
                          transition-colors duration-300
                          cursor-pointer
                        "
                      >
                        <RefreshCw className="w-5 h-5" />
                        Clear & Restart
                      </motion.button>
                    </motion.div>
                  )}

                  {status === "approved" && (
                    <motion.div
                      key="approved"
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.95 }}
                      className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl bg-green-500/10 border border-green-500/30 text-green-400"
                    >
                      <CheckCircle2 className="w-5 h-5" />
                      <span className="font-bold text-sm tracking-wider uppercase">
                        Deployed Successfully
                      </span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
        
        {status === "idle" && streamedTasks.length === 0 && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="glass-card rounded-2xl p-12 flex flex-col items-center justify-center text-center border-dashed border-white/10 mt-6"
          >
            <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-4">
              <Sparkles className="w-8 h-8 text-slate-600" />
            </div>
            <h3 className="text-white font-semibold mb-2">Ready to Assemble Crew</h3>
            <p className="text-slate-500 text-sm max-w-xs">
              Enter a topic above and launch the agent pipeline to generate comprehensive content.
            </p>
          </motion.div>
        )}
      </div>
    </section>
  );
}
