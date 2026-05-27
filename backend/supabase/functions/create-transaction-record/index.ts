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

  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const user = await getAuthenticatedUser(req);
    const adminKey = Deno.env.get("TRACE_ADMIN_API_KEY");
    const providedAdminKey = req.headers.get("x-trace-admin-key");

    if (!adminKey || providedAdminKey !== adminKey) {
      return jsonResponse({ error: "Trace transaction recording requires admin authorization" }, 403);
    }

    const body = await req.json();
    const amountTrace = Number(body.amount_trace);
    const transactionType = String(body.transaction_type ?? "").trim();
    const source = String(body.source ?? "").trim();
    const provenance = body.provenance;

    if (!Number.isFinite(amountTrace) || amountTrace === 0) {
      return jsonResponse({ error: "amount_trace must be a non-zero number" }, 400);
    }

    if (!transactionType) {
      return jsonResponse({ error: "transaction_type is required" }, 400);
    }

    if (!source) {
      return jsonResponse({ error: "source is required" }, 400);
    }

    if (!provenance || Array.isArray(provenance) || typeof provenance !== "object" || Object.keys(provenance).length === 0) {
      return jsonResponse({ error: "provenance must be a non-empty object" }, 400);
    }

    const supabase = createServiceClient();
    const { data, error } = await supabase.rpc("record_trace_transaction", {
      p_user_id: user.id,
      p_amount_trace: amountTrace,
      p_transaction_type: transactionType,
      p_source: source,
      p_provenance: provenance,
      p_payment_rail: body.payment_rail ?? "fiat",
      p_payment_provider: body.payment_provider ?? null,
      p_payment_provider_reference: body.payment_provider_reference ?? null,
      p_settlement_currency: body.settlement_currency ?? "USD",
      p_settlement_amount: body.settlement_amount ?? null,
    });

    if (error) {
      return jsonResponse({ error: error.message }, 400);
    }

    return jsonResponse({ transaction: data }, 201);
  } catch (error) {
    return jsonResponse({ error: getErrorMessage(error) }, 401);
  }
});
