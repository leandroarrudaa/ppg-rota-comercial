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
  return base + risco + bonusAtraso(c);
}

// ---------------------------------------------------------------
// Agenda de visita. O backend calcula proximaVisita a partir do que o
// vendedor combinou no relatório ("voltar em X dias"); sem combinação, cai
// na cadência da faixa. Nulo = nunca visitado.
// ---------------------------------------------------------------

// dias de atraso em relação à data em que valia voltar (0 se ainda não venceu)
export function diasDeAtraso(c, hoje = new Date()) {
  if (!c.proximaVisita) return 0; // nunca visitado: não está "atrasado", está livre
  const alvo = new Date(c.proximaVisita + "T00:00:00");
  return Math.max(0, Math.round((hoje - alvo) / 86400000));
}

// Cliente entra no plano se nunca foi visitado ou se já passou da data de
// voltar. É isto que impede o mesmo cliente de reaparecer na semana seguinte
// de uma visita — o problema que motivou toda esta parte.
export function estaNaHoraDeVisitar(c, hoje = new Date()) {
  if (!c.proximaVisita) return true;
  return new Date(c.proximaVisita + "T00:00:00") <= hoje;
}

// Quem está vencido há mais tempo sobe na fila: um Ouro 40 dias atrasado
// precisa vir antes de um Ouro que venceu ontem. O teto evita que um cliente
// esquecido há anos domine a rota inteira sozinho.
function bonusAtraso(c) {
  const atraso = diasDeAtraso(c);
  if (!atraso) return 0;
  return Math.min(atraso, 90) * 0.6;
}

// Texto curto do estado da agenda, para a lista do plano explicar por que o
// cliente está ali (ou por que sumiu).
export function textoAgenda(c) {
  if (!c.ultimaVisita) return "nunca visitado";
  const quando = new Date(c.ultimaVisita + "T00:00:00").toLocaleDateString("pt-BR", {
    day: "2-digit", month: "2-digit",
  });
  const atraso = diasDeAtraso(c);
  if (atraso > 0) return `visitado em ${quando} · voltar há ${atraso}d`;
  if (c.proximaVisita) {
    const alvo = new Date(c.proximaVisita + "T00:00:00").toLocaleDateString("pt-BR", {
      day: "2-digit", month: "2-digit",
    });
    return `visitado em ${quando} · voltar em ${alvo}`;
  }
  return `visitado em ${quando}`;
}

export function motivoVisita(c) {
  if (c.emRisco) return "Reativar — esfriou";
  if (c.faixa === "Ouro") return "Blindar relacionamento";
  if (c.faixa === "Prata") return "Fazer subir de faixa";
  return "Desenvolver";
}

// ordena uma lista de pontos pelo vizinho mais próximo, a partir de um início
export function vizinhoMaisProximo(pontos, inicio) {
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

// Refinamento 2-opt: destrava o zigue-zague que o vizinho-mais-próximo deixa
// pra trás (ele decide passo a passo, sem enxergar o problema todo — sobra
// gente espalhada pro fim e a rota cruza o próprio caminho). A cada volta,
// testa se inverter um trecho encurta a soma das duas pontas que ele troca;
// se encurtar, inverte, e repete até não achar mais melhoria (ou um teto de
// voltas, pra não travar em listas grandes). Mantém o primeiro ponto fixo —
// é o início escolhido por quem chamou (seed do dia, ou o primeiro
// selecionado na Rota do Dia) — e é rota aberta: não fecha ciclo de volta
// pro começo.
export function refinar2opt(ordem) {
  const n = ordem.length;
  if (n < 4) return ordem;
  let rota = [...ordem];
  let melhorou = true;
  let voltas = 0;
  while (melhorou && voltas < 30) {
    melhorou = false;
    voltas++;
    for (let i = 1; i < n - 1; i++) {
      for (let k = i; k < n - 1; k++) {
        const a = rota[i - 1], b = rota[i], c = rota[k], d = rota[k + 1];
        const atual = distKm(a, b) + distKm(c, d);
        const trocado = distKm(a, c) + distKm(b, d);
        if (trocado < atual - 1e-6) {
          rota = [...rota.slice(0, i), ...rota.slice(i, k + 1).reverse(), ...rota.slice(k + 1)];
          melhorou = true;
        }
      }
    }
  }
  return rota;
}

// Monta o plano da semana: 5 dias, cada um uma rota geograficamente tight,
// ancorada num cliente de alto valor e completada por proximidade + valor.
//
// raioDiaKm e penalidadeKm vêm dos Ajustes (configuráveis pelo Admin, ver
// backend/app/services/configuracoes.py) — os padrões aqui só cobrem quem
// chama sem ter carregado a configuração ainda. penalidadeKm é quem
// realmente decide "pula o Prata do lado pra ir num Ouro mais longe": é
// quanto 1 km a mais custa frente ao valor do cliente nessa comparação.
export function montarPlanoSemana(
  clientes, capacidade, dias = 5, incluirNaoVencidos = false,
  { raioDiaKm = 45, penalidadeKm = 3 } = {}
) {
  // Fora do plano quem foi visitado há pouco e ainda não venceu. Sem isto, o
  // mesmo cliente reaparecia toda semana, porque o cálculo só olhava faixa e
  // risco — nunca a visita que acabou de acontecer.
  //
  // Também fora quem geo=="cidade": o geocodificador não achou nem a rua nem
  // o CEP e caiu no centro da cidade (ver scripts/02_geocodificar.py) — todo
  // mundo nessa situação cai EXATAMENTE no mesmo ponto. Pro algoritmo isso
  // parece uma região densíssima (dezenas de clientes a 0km um do outro) e
  // ele monta o dia inteiro em cima desse espelhismo, sem visitar endereço
  // real nenhum. geo=="cep" fica: cada CEP tem coordenada própria, não
  // empilha todo mundo no mesmo ponto — é impreciso, mas não é fantasma.
  const pool = clientes.filter(
    (c) => c.lat != null && c.geo !== "cidade" && (incluirNaoVencidos || estaNaHoraDeVisitar(c))
  );
  const restante = [...pool];
  const PENALIDADE_KM = penalidadeKm; // quanto a distância "custa" frente ao valor
  const RAIO_DIA_KM = raioDiaKm; // cada dia é uma rota local — sem cruzar o estado
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

    // 5) ordem: vizinho mais próximo a partir da semente, depois 2-opt pra
    // desfazer os cruzamentos que o vizinho-mais-próximo sozinho deixa —
    // isto ainda é linha reta; a ordem final "de estrada" (OSRM /trip) vem
    // depois, de forma assíncrona (ver otimizarRotaEstrada).
    const ordem = refinar2opt(vizinhoMaisProximo(escolhidos, seed));

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

// Reordena os pontos pela rota de estrada mais curta DE VERDADE — usa o
// serviço "trip" do OSRM (mesmo servidor gratuito de antes), que resolve a
// melhor sequência considerando a malha viária real (mão única, rio,
// rodovia), em vez da linha reta que vizinhoMaisProximo/refinar2opt usam.
// É por isso que substitui o antigo rotaEstrada, que só desenhava o
// caminho sem nunca mudar a ordem calculada em linha reta.
//
// Mantém o primeiro ponto como início — é o combinado (seed do dia no
// Plano da Semana, ou o primeiro cliente selecionado na Rota do Dia) — e
// não fecha ciclo: não precisa voltar pro início, só terminar no ponto que
// render a rota mais curta.
//
// Quem chama trata a falha (rede fora, serviço gratuito fora do ar): a
// ordem em linha reta (vizinhoMaisProximo + refinar2opt), calculada na
// hora sem depender de rede, já fica na tela antes desta função responder,
// e continua valendo se ela falhar.
export async function otimizarRotaEstrada(pontos) {
  if (pontos.length < 2) return null;
  const coords = pontos.map((c) => `${c.lng},${c.lat}`).join(";");
  const url =
    "https://router.project-osrm.org/trip/v1/driving/" + coords +
    "?source=first&roundtrip=false&geometries=geojson&overview=full";
  const r = await fetch(url);
  if (!r.ok) throw new Error("OSRM " + r.status);
  const j = await r.json();
  const trip = j.trips?.[0];
  if (!trip || !j.waypoints) return null;
  // waypoint_index = posição de cada ponto de entrada na rota otimizada —
  // remonta a ordem final a partir disso.
  const ordem = j.waypoints
    .map((w, i) => [w.waypoint_index, pontos[i]])
    .sort((a, b) => a[0] - b[0])
    .map(([, ponto]) => ponto);
  return {
    ordem,
    km: trip.distance / 1000,
    min: trip.duration / 60,
    linha: trip.geometry.coordinates.map(([lng, lat]) => [lat, lng]),
  };
}

export const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
