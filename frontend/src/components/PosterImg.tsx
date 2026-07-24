import { useState } from "react";

import { posterUrl } from "../lib/api";

interface Props {
  itemId: string;
  title: string;
  eager?: boolean;
  className?: string;
}

/** Poster via the art proxy. The backend guarantees an image on every
 * request (SVG placeholder on failure), so there is no broken-image path. */
export function PosterImg({ itemId, title, eager = false, className = "" }: Props) {
  const [loaded, setLoaded] = useState(false);

  return (
    <div className={`overflow-hidden bg-riser ${className}`}>
      <img
        src={posterUrl(itemId)}
        alt={`${title} poster`}
        draggable={false}
        loading={eager ? "eager" : "lazy"}
        onLoad={() => setLoaded(true)}
        className={`h-full w-full object-cover transition-opacity duration-300 ${
          loaded ? "opacity-100" : "opacity-0"
        }`}
      />
    </div>
  );
}
