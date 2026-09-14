import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent,
} from "react";

export type OrbitProduct = {
  key: string;
  label: string;
  description: string;
  available: boolean;
  glyph: string;
};

export type OrbitMode = {
  key: string;
  label: string;
  en: string;
  tagline: string;
  items: OrbitProduct[];
};

type ProductOrbitProps = {
  modes: OrbitMode[];
  activeKey: string;
  onSelect: (key: string) => void;
  onEnter: (key: string) => void;
  canEnter: boolean;
};

type MeshParticle = {
  id: number;
  x: number;
  y: number;
  size: number;
  delay: number;
  duration: number;
  opacity: number;
};

type MeshLink = {
  id: number;
  x: number;
  y: number;
  width: number;
  angle: number;
  delay: number;
};

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function makeMeshParticles(count: number): MeshParticle[] {
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));

  return Array.from({ length: count }, (_, index) => {
    const radius = Math.sqrt((index + 0.5) / count) * 48;
    const angle = index * goldenAngle;
    const x = 50 + Math.cos(angle) * radius;
    const y = 50 + Math.sin(angle) * radius * 0.72;

    return {
      id: index,
      x,
      y,
      size: index % 13 === 0 ? 3.8 : index % 5 === 0 ? 2.8 : 1.8,
      delay: -((index % 19) * 0.22),
      duration: 7.8 + (index % 9) * 0.46,
      opacity: 0.34 + (index % 7) * 0.06,
    };
  });
}

function makeMeshLinks(count: number): MeshLink[] {
  return Array.from({ length: count }, (_, index) => {
    const angle = index * 137.5;
    const radius = 10 + (index % 11) * 3.7;
    const rad = (angle * Math.PI) / 180;

    return {
      id: index,
      x: 50 + Math.cos(rad) * radius,
      y: 50 + Math.sin(rad) * radius * 0.7,
      width: 34 + (index % 6) * 13,
      angle: angle + (index % 4) * 22,
      delay: -((index % 12) * 0.28),
    };
  });
}

export function ProductOrbit({
  modes,
  activeKey,
  onSelect,
  onEnter,
  canEnter,
}: ProductOrbitProps) {
  const [reduceMotion, setReduceMotion] = useState(prefersReducedMotion);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const particles = useRef(makeMeshParticles(132));
  const links = useRef(makeMeshLinks(44));

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = () => setReduceMotion(media.matches);
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, []);

  const flatItems = modes.flatMap((mode) => mode.items);
  const activeItem =
    flatItems.find((item) => item.key === activeKey) ??
    flatItems.find((item) => item.available) ??
    flatItems[0];
  const availableCount = flatItems.filter((item) => item.available).length;
  const entryCount = flatItems.length;
  const canRun = Boolean(activeItem?.available && canEnter);

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (reduceMotion) {
      return;
    }

    const element = stageRef.current;
    if (!element) {
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5) * 22;
    const y = ((event.clientY - rect.top) / rect.height - 0.5) * 18;
    element.style.setProperty("--mesh-pointer-x", `${x.toFixed(2)}px`);
    element.style.setProperty("--mesh-pointer-y", `${y.toFixed(2)}px`);
  }

  function handlePointerLeave() {
    const element = stageRef.current;
    if (!element) {
      return;
    }

    element.style.setProperty("--mesh-pointer-x", "0px");
    element.style.setProperty("--mesh-pointer-y", "0px");
  }

  function handleEnter() {
    if (!activeItem || !canRun) {
      return;
    }

    onSelect(activeItem.key);
    onEnter(activeItem.key);
  }

  if (!activeItem) {
    return null;
  }

  return (
    <div className="mesh-shell">
      <div
        aria-label="品类选择数据中心"
        className="mesh-stage"
        onPointerLeave={handlePointerLeave}
        onPointerMove={handlePointerMove}
        ref={stageRef}
      >
        <div className="mesh-backdrop" aria-hidden>
          <span className="mesh-grid" />
          <span className="mesh-ambient mesh-ambient-left" />
          <span className="mesh-ambient mesh-ambient-right" />
        </div>

        <div className="mesh-bridge mesh-bridge-left" aria-hidden>
          <span className="mesh-bridge-meta">CATEGORY ENTRY / 01</span>
          <span className="mesh-bridge-line">
            <span className="mesh-bridge-packet" />
          </span>
        </div>

        <div className="mesh-bridge mesh-bridge-right" aria-hidden>
          <span className="mesh-bridge-meta">ANALYZABLE / 01</span>
          <span className="mesh-bridge-line">
            <span className="mesh-bridge-packet" />
          </span>
        </div>

        <div className="mesh-vortex-wrap">
          <div className="mesh-vortex-disc" aria-hidden>
            <span className="mesh-vortex-ring mesh-vortex-ring-a" />
            <span className="mesh-vortex-ring mesh-vortex-ring-b" />
            <span className="mesh-vortex-ring mesh-vortex-ring-c" />
            <span className="mesh-vortex-inner">
              {links.current.map((link) => (
                <span
                  className="mesh-link"
                  key={link.id}
                  style={
                    {
                      "--mesh-link-x": `${link.x}%`,
                      "--mesh-link-y": `${link.y}%`,
                      "--mesh-link-width": `${link.width}px`,
                      "--mesh-link-angle": `${link.angle}deg`,
                      "--mesh-link-delay": `${link.delay}s`,
                    } as CSSProperties
                  }
                />
              ))}
              {particles.current.map((particle) => (
                <span
                  className="mesh-particle"
                  key={particle.id}
                  style={
                    {
                      "--mesh-particle-x": `${particle.x}%`,
                      "--mesh-particle-y": `${particle.y}%`,
                      "--mesh-particle-size": `${particle.size}px`,
                      "--mesh-particle-delay": `${particle.delay}s`,
                      "--mesh-particle-duration": `${particle.duration}s`,
                      "--mesh-particle-opacity": particle.opacity,
                    } as CSSProperties
                  }
                />
              ))}
            </span>
          </div>

          <div className="mesh-vortex-label">
            <span className="mesh-vortex-kicker">ACTIVE CATEGORY</span>
            <strong>{activeItem.label}</strong>
            <span>{canRun ? "后端链路已接入" : "敬请期待"}</span>
          </div>
        </div>

        <div className="mesh-stat mesh-stat-left">
          <span>{entryCount}</span>
          <strong>品类入口</strong>
        </div>
        <div className="mesh-stat mesh-stat-right">
          <span>{availableCount}</span>
          <strong>可分析</strong>
        </div>

        <button
          className="mesh-cta"
          disabled={!canRun}
          onClick={handleEnter}
          type="button"
        >
          <span className="mesh-cta-fill" />
          <span className="mesh-cta-text">
            {canRun ? "进入分析" : "敬请期待"}
          </span>
          <span className="mesh-cta-sub">{activeItem.description}</span>
        </button>
      </div>
    </div>
  );
}
