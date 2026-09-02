interface HeaderProps {
  onLogoClick?: () => void;
}

export function Header({ onLogoClick }: HeaderProps) {
  return (
    <header className="h-16 border-b bg-card flex items-center px-6 z-10 flex-shrink-0 relative">
      {/* Logo — left, clickable, navigates back */}
      <button
        onClick={onLogoClick}
        className="flex items-center cursor-pointer bg-transparent border-0 p-0 z-10"
      >
        <img
          src="/futuraiq-logo.svg"
          alt="FuturAIQ"
          className="h-9 object-contain"
        />
      </button>

      {/* Title — absolute center, non-clickable */}
      <div className="absolute left-1/2 -translate-x-1/2 pointer-events-none">
        <span className="font-serif font-normal text-lg text-primary tracking-tight">
          Earnings Call Intelligence
        </span>
      </div>
    </header>
  );
}
