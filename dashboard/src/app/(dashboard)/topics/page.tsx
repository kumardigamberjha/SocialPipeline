"use client";

import SavedTopicList from "@/components/topics/SavedTopicList";

export default function TopicsPage() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <SavedTopicList />
    </div>
  );
}
