/** Moods: the human way to pick genres. Selecting a mood ticks its genres
 * into the filter; the genres themselves stay editable under a disclosure.
 * Purely a presentation concept — the API only ever sees genres. */

export interface Mood {
  id: string;
  emoji: string;
  label: string;
  genres: string[];
}

export const MOODS: Mood[] = [
  { id: "laugh", emoji: "😂", label: "Make me laugh", genres: ["Comedy"] },
  {
    id: "edge",
    emoji: "🔪",
    label: "Edge of the seat",
    genres: ["Thriller", "Suspense", "Mystery", "Crime"],
  },
  { id: "scare", emoji: "👻", label: "Scare me", genres: ["Horror"] },
  { id: "big-night", emoji: "🍿", label: "Big night in", genres: ["Action", "Adventure"] },
  { id: "feels", emoji: "💛", label: "All the feels", genres: ["Romance", "Drama"] },
  {
    id: "another-world",
    emoji: "🚀",
    label: "Another world",
    genres: ["Science Fiction", "Fantasy"],
  },
  {
    id: "family",
    emoji: "🧸",
    label: "Family night",
    genres: ["Family", "Animation", "Children"],
  },
  {
    id: "think",
    emoji: "🧠",
    label: "Make me think",
    genres: ["Documentary", "Biography", "History"],
  },
  { id: "song-dance", emoji: "🎵", label: "Song and dance", genres: ["Music", "Musical"] },
  { id: "grit", emoji: "🤠", label: "Old-school grit", genres: ["Western", "War"] },
];
