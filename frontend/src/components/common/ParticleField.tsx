import { useEffect, useRef } from "react";

type ParticleFieldProps = {
  /** 定位 / 层级由外部 className 控制（如 "absolute inset-0"）。 */
  className?: string;
  /** 粒子密度系数，默认 1。 */
  density?: number;
};

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  a: number;
};

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// 自研 canvas 粒子背景（无第三方库）：缓慢漂浮 + 近邻连线，靛青配色。
export function ParticleField({ className = "", density = 1 }: ParticleFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) {
      return;
    }
    const context = canvasEl.getContext("2d");
    if (!context) {
      return;
    }
    const canvas: HTMLCanvasElement = canvasEl;
    const ctx: CanvasRenderingContext2D = context;

    const reduced = prefersReducedMotion();
    let width = 0;
    let height = 0;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let particles: Particle[] = [];
    let raf = 0;

    function spawn(): Particle {
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16 - 0.04,
        r: Math.random() * 1.5 + 0.6,
        a: Math.random() * 0.45 + 0.25,
      };
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      if (width === 0 || height === 0) {
        return;
      }
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const target = Math.min(
        72,
        Math.max(18, Math.floor(((width * height) / 26000) * density)),
      );
      particles = Array.from({ length: target }, spawn);
    }

    const LINK = 122;

    function draw() {
      ctx.clearRect(0, 0, width, height);

      // 近邻连线
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const q = particles[j];
          const dx = p.x - q.x;
          const dy = p.y - q.y;
          const dist2 = dx * dx + dy * dy;
          if (dist2 < LINK * LINK) {
            const alpha = (1 - dist2 / (LINK * LINK)) * 0.1;
            ctx.strokeStyle = `rgba(125, 211, 252, ${alpha})`;
            ctx.lineWidth = 0.55;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
      }

      // 粒子（带柔光）
      ctx.shadowColor = "rgba(56, 189, 248, 0.75)";
      ctx.shadowBlur = 6;
      for (const p of particles) {
        ctx.beginPath();
        ctx.fillStyle = `rgba(160, 205, 255, ${p.a})`;
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.shadowBlur = 0;
    }

    function step() {
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -12) p.x = width + 12;
        if (p.x > width + 12) p.x = -12;
        if (p.y < -12) p.y = height + 12;
        if (p.y > height + 12) p.y = -12;
      }
      draw();
      raf = window.requestAnimationFrame(step);
    }

    resize();
    if (reduced) {
      draw();
    } else {
      step();
    }

    function handleResize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      resize();
      if (reduced) {
        draw();
      }
    }
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (raf) {
        window.cancelAnimationFrame(raf);
      }
    };
  }, [density]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={className}
      style={{ display: "block", width: "100%", height: "100%" }}
    />
  );
}
