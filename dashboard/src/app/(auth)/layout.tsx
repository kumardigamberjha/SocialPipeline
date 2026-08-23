export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-xl font-semibold text-slate-100">Wings of AI</h1>
          <p className="mt-1 text-sm text-slate-500">Command Nexus</p>
        </div>
        {children}
      </div>
    </div>
  );
}
