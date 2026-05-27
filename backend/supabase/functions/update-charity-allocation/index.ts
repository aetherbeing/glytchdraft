import {
  createServiceClient,
  getErrorMessage,
  getAuthenticatedUser,
  handleOptions,
  jsonResponse,
} from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  const optionsResponse = handleOptions(req);
  if (optionsResponse) return optionsResponse;

  if (req.method !== "PATCH" && req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const user = await getAuthenticatedUser(req);
    const body = await req.json();
    const percentage = Number(body.charity_allocation_percentage);

    if (!Number.isFinite(percentage) || percentage < 0 || percentage > 50) {
      return jsonResponse({ error: "charity_allocation_percentage must be between 0 and 50" }, 400);
    }

    const supabase = createServiceClient();
    await supabase.from("users").upsert({ id: user.id }, { onConflict: "id" });

    const { data, error } = await supabase
      .from("users")
      .update({ charity_allocation_percentage: percentage })
      .eq("id", user.id)
      .select("id, charity_allocation_percentage, updated_at")
      .single();

    if (error) {
      return jsonResponse({ error: error.message }, 400);
    }

    return jsonResponse({ user: data });
  } catch (error) {
    return jsonResponse({ error: getErrorMessage(error) }, 401);
  }
});
