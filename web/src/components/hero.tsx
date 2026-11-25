import { motion } from "motion/react";

import { Composer } from "@/components/composer";
import { TiltedGridHero } from "@/components/ui/tilted-grid-hero";
import type { CreateJobInput, Trends } from "@/lib/api";

const IMAGES = [
  { src: "https://images.unsplash.com/photo-1492619375914-88005aa9e8fb?auto=format&fit=crop&w=900&q=72", alt: "Crowd under stage lights" },
  { src: "https://images.unsplash.com/photo-1478720568477-152d9b164e26?auto=format&fit=crop&w=900&q=72", alt: "Cinema seats and a lit screen" },
  { src: "https://images.unsplash.com/photo-1524253482453-3fed8d2fe12b?auto=format&fit=crop&w=900&q=72", alt: "Editor cutting footage on a timeline" },
  { src: "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?auto=format&fit=crop&w=900&q=72", alt: "Recording studio microphone" },
  { src: "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?auto=format&fit=crop&w=900&q=72", alt: "Concert lights" },
  { src: "https://images.unsplash.com/photo-1574717024653-61fd2cf4d44d?auto=format&fit=crop&w=900&q=72", alt: "Film strip and projector" },
  { src: "https://images.unsplash.com/photo-1485846234645-a62644f84728?auto=format&fit=crop&w=900&q=72", alt: "Camera on a film set" },
  { src: "https://images.unsplash.com/photo-1524368535928-5b5e00ddc76b?auto=format&fit=crop&w=900&q=72", alt: "Podcast host at the mic" },
  { src: "https://images.unsplash.com/photo-1516280440614-37939bbacd81?auto=format&fit=crop&w=900&q=72", alt: "Studio headphones" },
  { src: "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=900&q=72", alt: "Audience silhouettes" },
];

interface HeroProps {
  trends: Trends | null;
  ready: boolean;
  submitting: boolean;
  onCreate: (input: CreateJobInput) => Promise<void>;
}

export function Hero({ trends, ready, submitting, onCreate }: HeroProps) {
  return (
    <TiltedGridHero
      images={IMAGES}
      tileHeight={28}
      axis={60}
      curve={72}
      gap={6}
      fade={15}
      speed={5}
      className="h-[660px] w-full sm:h-[720px]"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-[1]"
        style={{
          background:
            "radial-gradient(50% 46% at 50% 56%, rgba(7,8,11,0.93) 0%, rgba(7,8,11,0.74) 42%, rgba(7,8,11,0.18) 70%, transparent 100%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 z-[1] h-36 bg-gradient-to-b from-background via-background/70 to-transparent"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-40 bg-gradient-to-t from-background to-transparent"
      />

      <div className="relative z-10 mx-auto flex h-full w-full max-w-5xl flex-col items-center px-5">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="max-w-2xl pt-16 text-center sm:pt-20"
        >
          <span className="inline-flex items-center gap-2 rounded-full border border-brand/20 bg-brand/[0.06] px-3 py-1 text-[10.5px] font-semibold uppercase tracking-[0.16em] text-brand">
            <span className="size-1.5 rounded-full bg-brand" />
            local pipeline · yt-dlp → whisper.cpp → ffmpeg
          </span>

          <h1 className="mt-5 text-balance text-[38px] font-semibold leading-[1.03] tracking-[-0.035em] text-foreground sm:text-5xl lg:text-[56px]">
            Long videos in.
            <br />
            Vertical clips{" "}
            <span className="bg-gradient-to-r from-brand via-[#7ef0b0] to-[#8b5cff] bg-clip-text text-transparent">
              out.
            </span>
          </h1>

          <p className="mx-auto mt-4 max-w-lg text-balance text-sm leading-relaxed text-muted-foreground sm:text-[15px]">
            Paste a link. ClipForge finds the moments worth keeping, cuts them to 9:16 and
            burns in word-by-word captions — without sending a frame off this machine.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
          className="mt-9 w-full max-w-[760px]"
        >
          <Composer
            trends={trends}
            ready={ready}
            submitting={submitting}
            onCreate={onCreate}
          />
        </motion.div>

        <div className="mt-auto flex w-full flex-col items-center gap-2 pb-7 pt-10 text-[11px] text-muted-foreground/70 sm:flex-row sm:justify-between">
          <span className="font-medium tracking-wide">
            yt-dlp <span className="px-1 text-white/20">·</span> whisper.cpp
            <span className="px-1 text-white/20">·</span> ffmpeg
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-brand/70" />
            100% local · no API keys
          </span>
        </div>
      </div>
    </TiltedGridHero>
  );
}
