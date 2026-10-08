import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { login, register as registerAccount } from "../api/generated/sdk.gen";
import { errorMessage } from "../api/queries";
import { queryClient } from "../app/router";
import { ErrorBox, Footer, Logo } from "../components/shared";

export function Auth({ register = false }: { register?: boolean }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: async () =>
      (
        await (register ? registerAccount : login)({
          body: { email, password },
        })
      ).data!,
    onSuccess: (user) => {
      queryClient.setQueryData(["me"], user);
      navigate("/app");
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }
  return (
    <div className="shell">
      <header className="public-header">
        <Logo />
        <Link className="text-link" to="/">
          Back to home
        </Link>
      </header>
      <main className="auth-main">
        <div className="auth-card">
          <span className="eyebrow">YOUR NEXT READ STARTS HERE</span>
          <h1>{register ? "Create your account." : "Welcome back."}</h1>
          <p>
            {register
              ? "A small step toward clearer contracts."
              : "Pick up where your analysis left off."}
          </p>
          <form onSubmit={submit}>
            <label>
              Email address
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                required
                minLength={10}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 10 characters"
              />
            </label>
            {mutation.isError && (
              <ErrorBox message={errorMessage(mutation.error)} />
            )}
            <button className="button full" disabled={mutation.isPending}>
              {mutation.isPending
                ? "Please wait…"
                : register
                  ? "Create account"
                  : "Sign in"}
              <ArrowRight size={18} />
            </button>
          </form>
          <div className="auth-switch">
            {register ? "Already have an account?" : "New to Radar?"}{" "}
            <Link to={register ? "/login" : "/register"}>
              {register ? "Sign in" : "Create an account"}
            </Link>
          </div>
          <div className="subtle-note">
            <ShieldCheck size={15} /> English and German rental contract demo.
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}
