interface ProcessingAnimationProps {
  message?: string
}

export function ProcessingAnimation({
  message = 'Auditing documents\u2026',
}: ProcessingAnimationProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 select-none">
      {/* Orbit track + lens */}
      <div className="relative w-[100px] h-[100px] mb-6">
        {/* Dashed orbit ring */}
        <svg
          className="absolute inset-0 w-full h-full animate-[spin_3s_linear_infinite]"
          viewBox="0 0 100 100"
          fill="none"
        >
          <circle
            cx="50"
            cy="50"
            r="42"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 6"
            className="text-teal-600/30"
          />
        </svg>

        {/* Magnifying glass orbiting */}
        <svg
          className="absolute inset-0 w-full h-full animate-[spin_2s_linear_infinite]"
          viewBox="0 0 100 100"
          fill="none"
        >
          {/* Lens glow */}
          <circle
            cx="50"
            cy="8"
            r="6"
            className="text-teal-600/20"
            stroke="currentColor"
            strokeWidth="2"
          />
          <circle
            cx="50"
            cy="8"
            r="4"
            className="text-teal-600"
            fill="currentColor"
          />
          {/* Handle */}
          <line
            x1="53"
            y1="11"
            x2="62"
            y2="20"
            className="text-teal-600"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </svg>

        {/* Center dot */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-1.5 h-1.5 rounded-full bg-teal-600/40 animate-pulse" />
        </div>
      </div>

      {/* Scanning line */}
      <div className="relative w-[120px] h-[2px] mb-4 overflow-hidden rounded-full bg-teal-600/10">
        <div className="absolute inset-0 animate-[scan_1.5s_ease-in-out_infinite] w-[40%] rounded-full bg-teal-600/40" />
      </div>

      <p className="text-[13px] text-muted font-medium tracking-wide">{message}</p>
    </div>
  )
}
