import { redirect } from "next/navigation";

// /admin used to host the OpenAI-vs-Fuel IX compare chat. That page was retired with the move
// to Fuel IX only (see archive/openai/), so this route now lands on the first admin tool.
export default function AdminPage() {
  redirect("/admin/batch");
}
