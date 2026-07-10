// ============================================================
// Motor de roteirização — equilíbrio entre VALOR (RFM) e ECONOMIA (km)
// ============================================================

const RAIO_TERRA = 6371; // km

export function distKm(a, b) {
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const la1 = (a.lat * Math.PI) / 180;
  const la2 = (b.lat * Math.PI) / 180;
  const x =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2;
  return 2 * RAIO_TERRA * Math.asin(Math.sqrt(x));
}

// valor estratégico de visitar o cliente
export function valorEstrategico(c) {
  const base = { Ouro: 100, Prata: 45, Bronze: 18 }[c.faixa] || 10;
  const risco = c.emRisco ? 70 : 0; // reativar quem esfriou é prioridade
  return base + risco;
}

export function motivoVisita(c) {
  if (c.emRisco) return "Reativar — esfriou";
  if (c.faixa === "Ouro") return "Blindar relacionamento";
  if (c.faixa === "Prata") return "Fazer subir de faixa";
  return "Desenvolver";
}

// ordena uma lista de pontos pelo vizinho mais próximo, a partir de um início
function vizinhoMaisProximo(pontos, inicio) {
  const restantes = [...pontos];
  const ordem = [];
  let atual = inicio;
  // remove o início da lista de restantes
  const idx0 = restantes.findIndex((p) => p.id === inicio.id);
  if (idx0 >= 0) restantes.splice(idx0, 1);
  ordem.push(atual);
  while (restantes.length) {
    let melhor = 0;
    let melhorD = Infinity;
    for (let i = 0; i < restantes.length; i++) {
      const d = distKm(atual, restantes[i]);
      if (d < melhorD) {
        melhorD = d;
        melhor = i;
      }
    }
    atual = restantes.splice(melhor, 1)[0];
    ordem.push(atual);
  }
  return ordem;
}

export function kmTotalReta(ordem) {
  let km = 0;
  for (let i = 1; i < ordem.length; i++) km += distKm(ordem[i - 1], ordem[i]);
  return km;
}

// Monta o plano da semana: 5 dias, cada um uma rota geograficamente tight,
// ancorada num cliente de alto valor e completada por proximidade + valor.
export function montarPlanoSemana(clientes, capacidade, dias = 5) {
  const pool = clientes.filter((c) => c.lat != null);
  const restante = [...pool];
  const PENALIDADE_KM = 3; // quanto a distância "custa" frente ao valor
  const RAIO_DIA_KM = 45; // cada dia é uma rota local — sem cruzar o estado
  const planos = [];

  // potencial de um dia ancorado em "seed": soma do valor dos melhores
  // clientes dentro do raio (favorece áreas densas E valiosas)
  function potencialDia(seed) {
    const locais = restante
      .filter((c) => distKm(seed, c) <= RAIO_DIA_KM)
      .map(valorEstrategico)
      .sort((a, b) => b - a);
    return locais.slice(0, capacidade).reduce((s, v) => s + v, 0);
  }

  for (let d = 0; d < dias && restante.length; d++) {
    // 1) semente = ponto que rende o melhor DIA INTEIRO (densidade + valor)
    let seed = restante[0];
    let melhorPot = -1;
    for (const c of restante) {
      const p = potencialDia(c);
      if (p > melhorPot) { melhorPot = p; seed = c; }
    }
    // 2) vizinhança LOCAL da semente (dentro do raio do dia)
    const vizinhanca = restante
      .filter((c) => c.id === seed.id || distKm(seed, c) <= RAIO_DIA_KM)
      .sort((a, b) => distKm(seed, a) - distKm(seed, b));
    const janela = vizinhanca.slice(0, Math.min(capacidade * 5, vizinhanca.length));
    // 3) ranqueia por (valor − custo de deslocamento)
    janela.sort(
      (a, b) =>
        valorEstrategico(b) - distKm(seed, b) * PENALIDADE_KM -
        (valorEstrategico(a) - distKm(seed, a) * PENALIDADE_KM)
    );
    const escolhidos = janela.slice(0, capacidade);
    // garante a semente na lista
    if (!escolhidos.find((c) => c.id === seed.id)) escolhidos.unshift(seed);

    // 4) remove do pool
    for (const c of escolhidos) {
      const i = restante.findIndex((x) => x.id === c.id);
      if (i >= 0) restante.splice(i, 1);
    }

    // 5) ordem ótima (vizinho mais próximo a partir da semente)
    const ordem = vizinhoMaisProximo(escolhidos, seed);

    planos.push({
      dia: d,
      seed,
      clientes: ordem,
      kmReta: kmTotalReta(ordem),
      valor: ordem.reduce((s, c) => s + (c.fat || 0), 0),
    });
  }
  return planos;
}

// Rota de estrada real via OSRM (gratuito). Mantém a ordem dada.
export async function rotaEstrada(ordem) {
  if (ordem.length < 2) return null;
  const coords = ordem.map((c) => `${c.lng},${c.lat}`).join(";");
  const url = `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`;
  const r = await fetch(url);
  if (!r.ok) throw new Error("OSRM " + r.status);
  const j = await r.json();
  const rota = j.routes?.[0];
  if (!rota) return null;
  return {
    km: rota.distance / 1000,
    min: rota.duration / 60,
    linha: rota.geometry.coordinates.map(([lng, lat]) => [lat, lng]),
  };
}

export const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
