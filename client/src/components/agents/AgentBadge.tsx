import { Cpu } from '@phosphor-icons/react';
import { cn } from '../../lib/utils';

interface AgentBadgeProps {
    name: string;
    muted?: boolean;
    className?: string;
}

export default function AgentBadge({ name, muted = false, className }: AgentBadgeProps) {
    return (
        <span
            className={cn(
                'inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-medium',
                muted
                    ? 'border-border bg-muted/60 text-muted-foreground'
                    : 'border-primary/20 bg-primary/10 text-primary',
                className,
            )}
        >
            <Cpu weight="fill" className="h-3 w-3 shrink-0" />
            <span className="truncate">{name}</span>
        </span>
    );
}
