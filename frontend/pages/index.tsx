import React from "react";

import ChatPanel from "../components/ChatPanel";

const DEFAULT_TENANT = "default";

export default function Home() {
  return (
    <main>
      <div className="chat-container" role="main">
        <ChatPanel tenantId={DEFAULT_TENANT} />
      </div>
    </main>
  );
}
