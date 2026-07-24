import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AlbumScreen } from "./screens/Album";
import { DeckScreen } from "./screens/Deck";
import { FinalRoundScreen } from "./screens/FinalRound";
import { HomeScreen } from "./screens/Home";
import { JoinScreen } from "./screens/Join";
import { LobbyScreen } from "./screens/Lobby";
import { MatchesScreen } from "./screens/Matches";
import { SettingsScreen } from "./screens/Settings";
import { SetupScreen } from "./screens/Setup";
import { SetupWizardScreen } from "./screens/SetupWizard";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeScreen />} />
        <Route path="/setup" element={<SetupWizardScreen />} />
        <Route path="/settings" element={<SettingsScreen />} />
        <Route path="/solo" element={<SetupScreen />} />
        <Route path="/new" element={<SetupScreen />} />
        <Route path="/join" element={<JoinScreen />} />
        <Route path="/join/:code" element={<JoinScreen />} />
        <Route path="/session/:sessionId/lobby" element={<LobbyScreen />} />
        <Route path="/session/:sessionId/swipe" element={<DeckScreen />} />
        <Route path="/session/:sessionId/matches" element={<MatchesScreen />} />
        <Route path="/session/:sessionId/final" element={<FinalRoundScreen />} />
        <Route path="/album" element={<AlbumScreen />} />
      </Routes>
    </BrowserRouter>
  );
}
