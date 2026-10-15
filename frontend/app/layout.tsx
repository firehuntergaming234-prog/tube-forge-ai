import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: {
    default: 'Tube Forge AI — Make Every Moment Viral',
    template: '%s | Tube Forge AI',
  },
  description: 'Turn long videos into scroll-stopping Shorts, Reels, and creator-ready clips with Tube Forge AI.',
  applicationName: 'Tube Forge AI',
  keywords: ['AI video clips', 'YouTube Shorts', 'Instagram Reels', 'video editor', 'creator tools'],
  openGraph: {
    title: 'Tube Forge AI — Make Every Moment Viral',
    description: 'Forge your next viral moment from any video you own or are allowed to edit.',
    siteName: 'Tube Forge AI',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Tube Forge AI — Make Every Moment Viral',
    description: 'Turn long videos into scroll-stopping clips.',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
