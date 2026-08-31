import { useState } from "react";

// Ações de uma visita aberta: finalizar (leva ao relatório) ou cancelar
// (abandona). Usado em dois lugares — na barra fixa do topo do app e dentro
// da ficha de outro cliente, quando a visita aberta é o que está impedindo
// de começar uma nova.
//
// O cancelar existe porque a visita aberta bloqueia todas as outras: sem
// saída, uma visita esquecida (celular descarregou, saiu do app antes de
// finalizar) deixa o vendedor travado em campo sem entender o porquê.
export default function VisitaEmAndamento({ visita, nomeCliente, aoFinalizar, aoCancelar, compacto }) {
  const [ocupado, setOcupado] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [erro, setErro] = useState("");

  async function executar(acao, qual) {
    setOcupado(qual);
    setErro("");
    try {
      await acao();
    } catch (e) {
      setErro(e.message);
    } finally {
      setOcupado("");
      setConfirmando(false);
    }
  }

  const horaInicio = visita?.inicio
    ? new Date(visita.inicio + "Z").toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className={"visita-andamento" + (compacto ? " compacto" : "")}>
      {!compacto && (
        <span className="visita-andamento-texto">
          <b>Visita em andamento</b>
          {nomeCliente ? <> em {nomeCliente}</> : null}
          {horaInicio ? <span className="faint"> · desde {horaInicio}</span> : null}
        </span>
      )}

      <div className="visita-andamento-acoes">
        <button
          className="btn btn-primary"
          onClick={() => executar(aoFinalizar, "finalizar")}
          disabled={Boolean(ocupado)}
        >
          {ocupado === "finalizar" ? "Finalizando…" : "Finalizar visita"}
        </button>

        {confirmando ? (
          <>
            <span className="faint" style={{ fontSize: 12 }}>Cancelar sem registrar nada?</span>
            <button
              className="btn btn-ghost"
              onClick={() => executar(aoCancelar, "cancelar")}
              disabled={Boolean(ocupado)}
            >
              {ocupado === "cancelar" ? "Cancelando…" : "Sim, cancelar"}
            </button>
            <button className="btn btn-ghost" onClick={() => setConfirmando(false)} disabled={Boolean(ocupado)}>
              Não
            </button>
          </>
        ) : (
          <button className="btn btn-ghost" onClick={() => setConfirmando(true)} disabled={Boolean(ocupado)}>
            Cancelar visita
          </button>
        )}
      </div>

      {erro && <div className="login-erro" style={{ marginTop: 6 }}>{erro}</div>}
    </div>
  );
}
