"use client";

import {
  Activity,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  KeyRound,
  Layers3,
  List,
  LogOut,
  MessageSquare,
  Shield,
  Sparkles,
  Target,
  Trash2,
  Upload,
  UserRound,
  XCircle
} from "lucide-react";
import Image from "next/image";
import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { apiDelete, apiGet, apiPost, apiUpload } from "@/lib/api";

const ENABLE_DEV_RAG = process.env.NEXT_PUBLIC_ENABLE_DEV_RAG === "true";
const REQUIRE_INVITE_CODE = process.env.NEXT_PUBLIC_REQUIRE_INVITE_CODE === "true";

type DocumentItem = {
  id: string;
  name: string;
  status: string;
  chunks: number;
  keywords: string[];
};

type Citation = {
  document_name: string;
  section: string;
  chunk_id: string;
  score: number;
};

type ChatResponse = {
  answer: string;
  source_label: "uploaded_materials" | "general_openai" | "hybrid";
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  metadata: Record<string, unknown>;
};

type RetrievedChunk = {
  id: string;
  document_name: string;
  section: string;
  text: string;
  score: number;
};

type Flashcard = {
  id?: string | null;
  question: string;
  answer: string;
  topic: string;
  source_label: string;
  interval_days?: number;
  due_at?: string | null;
  last_reviewed_at?: string | null;
  created_at?: string | null;
};

type QuizQuestion = {
  id: string;
  type: string;
  prompt: string;
  choices: string[];
  answer: string;
  topic: string;
  explanation: string;
};

type Quiz = {
  id: string;
  source_label: string;
  questions: QuizQuestion[];
  created_at?: string | null;
};

type WeakTopic = {
  topic: string;
  misses: number;
  attempts: number;
  accuracy: number;
  recommendation: string;
};

type StudyPlan = {
  id?: string | null;
  plan: string[];
  focus_topics: string[];
  metadata: Record<string, unknown>;
  created_at?: string | null;
};

type User = {
  id: string;
  email: string;
  created_at?: string | null;
};

type AuthResponse = {
  access_token: string;
  user: User;
};

type UploadState = {
  active: boolean;
  done: boolean;
  error: string;
  fileName: string;
  step: number;
};

const emptyPlan: StudyPlan = {
  focus_topics: ["upload materials", "ask a question", "take a quiz"],
  plan: [
    "Upload your first set of notes, slides, or transcript.",
    "Ask Cramly a question that should be answered from your material.",
    "Generate a short quiz and mark anything you miss.",
    "Review weak topics before creating your next study plan."
  ],
  metadata: { source: "empty_state" }
};

const uploadSteps = [
  "Adding your study material",
  "Reading the content",
  "Organizing it into study sections",
  "Preparing it for AI answers",
  "Ready to study"
];

function StudyAnswer({ answer, sourceLabel }: { answer: string; sourceLabel: ChatResponse["source_label"] }) {
  const normalized = normalizeAnswer(answer, sourceLabel);
  const lines = normalized.split(/\r?\n/);
  const nodes: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let listType: "ordered" | "unordered" | null = null;

  function flushParagraph() {
    if (!paragraph.length) return;
    nodes.push(
      <p key={`paragraph-${nodes.length}`} className="leading-7 text-slate-200">
        {renderInlineMarkdown(paragraph.join(" "))}
      </p>
    );
    paragraph = [];
  }

  function flushList() {
    if (!listType || !listItems.length) return;
    const ListTag = listType === "ordered" ? "ol" : "ul";
    nodes.push(
      <ListTag
        key={`list-${nodes.length}`}
        className={`${listType === "ordered" ? "list-decimal" : "list-disc"} ml-6 space-y-2 leading-7 text-slate-200`}
      >
        {listItems.map((item) => (
          <li key={item}>{renderInlineMarkdown(item)}</li>
        ))}
      </ListTag>
    );
    listItems = [];
    listType = null;
  }

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }

    if (["From your materials", "OpenAI general knowledge", "General explanation"].includes(trimmed)) {
      flushParagraph();
      flushList();
      nodes.push(
        <h3 key={`source-heading-${nodes.length}`} className="pt-2 text-lg font-semibold text-slate-50">
          {trimmed === "General explanation" ? "OpenAI general knowledge" : trimmed}
        </h3>
      );
      return;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      nodes.push(
        <h3 key={`heading-${nodes.length}`} className="pt-2 text-lg font-semibold text-slate-50">
          {renderInlineMarkdown(heading[2])}
        </h3>
      );
      return;
    }

    const ordered = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (ordered) {
      flushParagraph();
      if (listType !== "ordered") flushList();
      listType = "ordered";
      listItems.push(ordered[1]);
      return;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      flushParagraph();
      if (listType !== "unordered") flushList();
      listType = "unordered";
      listItems.push(unordered[1]);
      return;
    }

    flushList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();

  return <div className="space-y-4">{nodes}</div>;
}

function normalizeAnswer(answer: string, sourceLabel: ChatResponse["source_label"]) {
  const text = removeInternalChunkIds(answer).trim();
  const heading = sourceLabel === "general_openai" ? "OpenAI general knowledge" : sourceLabel === "uploaded_materials" ? "From your materials" : "";
  if (!heading) return text;
  if (text === heading) return "";
  return text.startsWith(`${heading}\n`) ? text.slice(heading.length).trimStart() : text;
}

function removeInternalChunkIds(text: string) {
  const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
  return text
    .replace(new RegExp(`\\s*\\((?:${uuid})(?:,\\s*${uuid})*\\)`, "g"), "")
    .replace(new RegExp(`\\s*\\[?(?:chunk|source)?\\s*${uuid}\\]?`, "gi"), "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/ {2,}/g, " ");
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+?\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`${part}-${index}`} className="font-semibold text-slate-50">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}

function messageFromError(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function flashcardKey(card: Flashcard) {
  return card.id || `${card.topic}-${card.question}`;
}

function formatSavedDate(value?: string | null) {
  if (!value) return "Saved study item";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

export default function Home() {
  const [showDashboard, setShowDashboard] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authError, setAuthError] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [accountDeleteConfirmation, setAccountDeleteConfirmation] = useState("");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [confirmingDocumentId, setConfirmingDocumentId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<"auto" | "materials" | "general" | "hybrid">("auto");
  const [depth, setDepth] = useState<"standard" | "advanced">("standard");
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [practicePanelOpen, setPracticePanelOpen] = useState(false);
  const [practiceSection, setPracticeSection] = useState<"focus" | "flashcards" | "quiz" | "weak">("focus");
  const [practiceMode, setPracticeMode] = useState<"flashcards" | "quiz">("flashcards");
  const [flashcardView, setFlashcardView] = useState<"due" | "saved">("due");
  const [flashcardDisplayMode, setFlashcardDisplayMode] = useState<"card" | "list">("card");
  const [currentFlashcardIndex, setCurrentFlashcardIndex] = useState(0);
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [savedFlashcards, setSavedFlashcards] = useState<Flashcard[]>([]);
  const [flippedCards, setFlippedCards] = useState<Record<string, boolean>>({});
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [quizDisplayMode, setQuizDisplayMode] = useState<"question" | "list">("question");
  const [currentQuizQuestionIndex, setCurrentQuizQuestionIndex] = useState(0);
  const [savedQuizzes, setSavedQuizzes] = useState<Quiz[]>([]);
  const [quizSelections, setQuizSelections] = useState<Record<string, string>>({});
  const [weakTopics, setWeakTopics] = useState<WeakTopic[]>([]);
  const [plan, setPlan] = useState<StudyPlan>(emptyPlan);
  const [devChunks, setDevChunks] = useState<RetrievedChunk[]>([]);
  const [uploadState, setUploadState] = useState<UploadState>({
    active: false,
    done: false,
    error: "",
    fileName: "",
    step: 0
  });
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("Sign in to make your study space private.");

  const sourceText = useMemo(() => {
    if (!chat) return "Ready";
    if (chat.source_label === "uploaded_materials") return "From your materials";
    if (chat.source_label === "hybrid") return "Materials plus OpenAI general knowledge";
    return "OpenAI general knowledge";
  }, [chat]);
  const answerDepth = chat?.metadata?.depth === "advanced" || chat?.metadata?.depth === "standard" ? chat.metadata.depth : depth;
  const depthText = answerDepth === "advanced" ? "Expert Mode" : "Study Mode";
  const uploadProgressPercent = uploadState.error || uploadState.done
    ? 100
    : Math.round(((uploadState.step + 1) / uploadSteps.length) * 100);
  const activeFlashcardIndex = cards.length ? Math.min(currentFlashcardIndex, cards.length - 1) : 0;
  const currentFlashcard = cards[activeFlashcardIndex] ?? null;
  const currentFlashcardNumber = currentFlashcard ? activeFlashcardIndex + 1 : 0;
  const quizQuestions = quiz?.questions ?? [];
  const activeQuizQuestionIndex = quizQuestions.length ? Math.min(currentQuizQuestionIndex, quizQuestions.length - 1) : 0;
  const currentQuizQuestion = quizQuestions[activeQuizQuestionIndex] ?? null;
  const currentQuizQuestionNumber = currentQuizQuestion ? activeQuizQuestionIndex + 1 : 0;

  useEffect(() => {
    const savedToken = window.localStorage.getItem("cramly_token");
    if (!savedToken) return;

    let cancelled = false;
    async function restoreSession() {
      try {
        const [sessionUser, docs, weak, studyPlan, dueCards, savedCards, quizzes] = await Promise.all([
          apiGet<User>("/api/auth/me", savedToken),
          apiGet<DocumentItem[]>("/api/documents", savedToken),
          apiGet<{ topics: WeakTopic[] }>("/api/weak-topics", savedToken),
          apiGet<StudyPlan>("/api/study-plan", savedToken),
          apiGet<{ cards: Flashcard[] }>("/api/flashcards/due", savedToken),
          apiGet<{ cards: Flashcard[] }>("/api/flashcards", savedToken),
          apiGet<Quiz[]>("/api/quizzes", savedToken)
        ]);
        if (cancelled) return;
        setToken(savedToken);
        setUser(sessionUser);
        setDocuments(docs);
        setWeakTopics(weak.topics);
        setPlan(studyPlan);
        setSavedFlashcards(savedCards.cards);
        setCards(dueCards.cards);
        setCurrentFlashcardIndex(0);
        setSavedQuizzes(quizzes);
        setQuiz(quizzes[0] ?? null);
        setCurrentQuizQuestionIndex(0);
        setQuizDisplayMode("question");
        setQuizSelections({});
        setNotice(`Private workspace for ${sessionUser.email}.`);
      } catch {
        window.localStorage.removeItem("cramly_token");
        if (cancelled) return;
        setToken(null);
        setUser(null);
        setNotice("Session expired. Sign in again.");
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  async function refresh(activeToken = token) {
    if (!activeToken) {
      setNotice("Sign in to load your private study data.");
      return;
    }
    try {
      const [docs, weak, studyPlan, dueCards, savedCards, quizzes] = await Promise.all([
        apiGet<DocumentItem[]>("/api/documents", activeToken),
        apiGet<{ topics: WeakTopic[] }>("/api/weak-topics", activeToken),
        apiGet<StudyPlan>("/api/study-plan", activeToken),
        apiGet<{ cards: Flashcard[] }>("/api/flashcards/due", activeToken),
        apiGet<{ cards: Flashcard[] }>("/api/flashcards", activeToken),
        apiGet<Quiz[]>("/api/quizzes", activeToken)
      ]);
      setDocuments(docs);
      setWeakTopics(weak.topics);
      setPlan(studyPlan);
      setSavedFlashcards(savedCards.cards);
      setCards(flashcardView === "saved" ? savedCards.cards : dueCards.cards);
      setCurrentFlashcardIndex(0);
      setFlashcardDisplayMode("card");
      setSavedQuizzes(quizzes);
      setQuiz(quizzes[0] ?? null);
      setCurrentQuizQuestionIndex(0);
      setQuizDisplayMode("question");
      setQuizSelections({});
      setNotice("Private study data synced.");
    } catch {
      setNotice("Session or API unavailable. Sign in again after the backend is running.");
    }
  }

  async function submitAuth(event: FormEvent) {
    event.preventDefault();
    setBusy("auth");
    setAuthError("");
    try {
      const payload = authMode === "register" && REQUIRE_INVITE_CODE
        ? { email, password, invite_code: inviteCode }
        : { email, password };
      const response = await apiPost<AuthResponse>(
        authMode === "login" ? "/api/auth/login" : "/api/auth/register",
        payload
      );
      window.localStorage.setItem("cramly_token", response.access_token);
      setToken(response.access_token);
      setUser(response.user);
      setPassword("");
      setInviteCode("");
      setNotice(`Private workspace ready for ${response.user.email}.`);
      await refresh(response.access_token);
    } catch (error) {
      setAuthError(messageFromError(error, authMode === "login" ? "Could not sign in with that email and password." : "Could not create that account."));
    } finally {
      setBusy("");
    }
  }

  function clearSession(nextNotice: string) {
    window.localStorage.removeItem("cramly_token");
    setToken(null);
    setUser(null);
    setDocuments([]);
    setConfirmingDocumentId(null);
    setChat(null);
    setPracticePanelOpen(false);
    setPracticeSection("focus");
    setPracticeMode("flashcards");
    setFlashcardView("due");
    setFlashcardDisplayMode("card");
    setCurrentFlashcardIndex(0);
    setCards([]);
    setSavedFlashcards([]);
    setFlippedCards({});
    setQuiz(null);
    setQuizDisplayMode("question");
    setCurrentQuizQuestionIndex(0);
    setSavedQuizzes([]);
    setQuizSelections({});
    setWeakTopics([]);
    setPlan(emptyPlan);
    setDevChunks([]);
    setCurrentPassword("");
    setNewPassword("");
    setAccountDeleteConfirmation("");
    setBusy("");
    setNotice(nextNotice);
  }

  function signOut() {
    clearSession("Signed out. Your next session starts private.");
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      setNotice("Sign in before asking Cramly.");
      return;
    }
    setBusy("chat");
    setNotice("Cramly is building your answer...");
    try {
      const response = await apiPost<ChatResponse>("/api/chat", { question, mode, depth }, token);
      setChat(response);
      setNotice("Answer ready with source labeling.");
    } catch {
      setChat(null);
      setNotice("Chat needs the backend running with a valid OPENAI_API_KEY.");
    } finally {
      setBusy("");
    }
  }

  async function uploadFile(file: File | undefined) {
    if (!file) return;
    if (!token) {
      setNotice("Sign in before uploading materials.");
      return;
    }
    setBusy("upload");
    setUploadState({ active: true, done: false, error: "", fileName: file.name, step: 0 });
    const progressTimer = window.setInterval(() => {
      setUploadState((current) => {
        if (!current.active || current.error || current.done) return current;
        return { ...current, step: Math.min(current.step + 1, uploadSteps.length - 2) };
      });
    }, 950);
    try {
      await apiUpload<DocumentItem>("/api/uploads", file, token);
      setUploadState({ active: false, done: true, error: "", fileName: file.name, step: uploadSteps.length - 1 });
      setNotice(`${file.name} indexed for study.`);
      await refresh();
    } catch (error) {
      const message = messageFromError(error, "Upload failed. Check the file type and backend settings.");
      setUploadState((current) => ({ ...current, active: false, done: false, error: message }));
      setNotice(message);
    } finally {
      window.clearInterval(progressTimer);
      setBusy("");
    }
  }

  async function deleteDocument(document: DocumentItem) {
    if (!token) {
      setNotice("Sign in before deleting materials.");
      return;
    }
    if (confirmingDocumentId !== document.id) {
      setConfirmingDocumentId(document.id);
      setNotice(`Confirm deletion for ${document.name}.`);
      return;
    }
    setBusy(`delete-document-${document.id}`);
    try {
      await apiDelete<{ ok: boolean }>(`/api/documents/${document.id}`, token);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      setConfirmingDocumentId(null);
      setNotice(`${document.name} deleted.`);
    } catch (error) {
      setNotice(messageFromError(error, "Could not delete that document."));
    } finally {
      setBusy("");
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setBusy("password");
    try {
      await apiPost<{ ok: boolean }>("/api/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword
      }, token);
      setCurrentPassword("");
      setNewPassword("");
      setNotice("Password updated.");
    } catch (error) {
      setNotice(messageFromError(error, "Could not update password."));
    } finally {
      setBusy("");
    }
  }

  async function deleteAccount() {
    if (!token || accountDeleteConfirmation !== "DELETE") return;
    setBusy("account-delete");
    try {
      await apiDelete<{ ok: boolean }>("/api/auth/account", token);
      clearSession("Account deleted.");
    } catch (error) {
      setNotice(messageFromError(error, "Could not delete account."));
      setBusy("");
    }
  }

  async function generateFlashcards() {
    if (!token) {
      setNotice("Sign in before generating flashcards.");
      return;
    }
    setPracticeMode("flashcards");
    setPracticeSection("flashcards");
    setPracticePanelOpen(true);
    setFlashcardView("due");
    setBusy("flashcards");
    try {
      const response = await apiPost<{ cards: Flashcard[] }>("/api/flashcards", {
        topic: question || "current study topic",
        source: "auto",
        count: 6
      }, token);
      setCards(response.cards);
      setCurrentFlashcardIndex(0);
      setFlashcardDisplayMode("card");
      setSavedFlashcards((current) => [...response.cards, ...current]);
      setFlippedCards({});
      setNotice("Flashcards saved. Tap a card to flip it.");
    } catch {
      setCards([]);
      setNotice("Flashcards need the backend running with OpenAI configured.");
    } finally {
      setBusy("");
    }
  }

  async function generateQuiz() {
    if (!token) {
      setNotice("Sign in before generating a quiz.");
      return;
    }
    setPracticeMode("quiz");
    setPracticeSection("quiz");
    setPracticePanelOpen(true);
    setBusy("quiz");
    try {
      const response = await apiPost<Quiz>("/api/quizzes", {
        topic: question || "current study topic",
        source: "auto",
        count: 4
      }, token);
      setQuiz(response);
      setCurrentQuizQuestionIndex(0);
      setQuizDisplayMode("question");
      setSavedQuizzes((current) => [response, ...current]);
      setQuizSelections({});
      setNotice("Quiz ready. Choose an option to reveal feedback.");
    } catch {
      setQuiz(null);
      setNotice("Quiz generation needs the backend running with OpenAI configured.");
    } finally {
      setBusy("");
    }
  }

  async function chooseQuizAnswer(questionItem: QuizQuestion, selectedAnswer: string) {
    if (!quiz || !token || quizSelections[questionItem.id]) return;
    const correct = selectedAnswer === questionItem.answer;
    setQuizSelections((current) => ({ ...current, [questionItem.id]: selectedAnswer }));
    try {
      const response = await apiPost<{ topics: WeakTopic[] }>("/api/quiz-attempts", {
        quiz_id: quiz.id,
        answers: [
          {
            question_id: questionItem.id,
            topic: questionItem.topic,
            selected_answer: selectedAnswer,
            correct_answer: questionItem.answer,
            correct
          }
        ]
      }, token);
      setWeakTopics(response.topics);
    } catch {
      setNotice("Weak-topic tracking needs the backend database running.");
    }
  }

  async function generateStudyPlan() {
    if (!token) {
      setNotice("Sign in before generating a study plan.");
      return;
    }
    setPracticeSection("focus");
    setPracticePanelOpen(true);
    setBusy("study-plan");
    try {
      const response = await apiPost<StudyPlan>("/api/study-plan", {}, token);
      setPlan(response);
      setNotice("Study plan refreshed.");
    } catch {
      setNotice("Study plan generation needs the backend running.");
    } finally {
      setBusy("");
    }
  }

  async function showDueFlashcards() {
    if (!token) return;
    setPracticeMode("flashcards");
    setPracticeSection("flashcards");
    setPracticePanelOpen(true);
    setFlashcardView("due");
    setBusy("flashcard-history");
    try {
      const response = await apiGet<{ cards: Flashcard[] }>("/api/flashcards/due", token);
      setCards(response.cards);
      setCurrentFlashcardIndex(0);
      setFlashcardDisplayMode("card");
      setFlippedCards({});
      setNotice(response.cards.length ? "Showing flashcards due today." : "No flashcards are due right now.");
    } catch {
      setNotice("Could not load due flashcards.");
    } finally {
      setBusy("");
    }
  }

  async function showSavedFlashcards() {
    if (!token) return;
    setPracticeMode("flashcards");
    setPracticeSection("flashcards");
    setPracticePanelOpen(true);
    setFlashcardView("saved");
    setBusy("flashcard-history");
    try {
      const response = await apiGet<{ cards: Flashcard[] }>("/api/flashcards", token);
      setSavedFlashcards(response.cards);
      setCards(response.cards);
      setCurrentFlashcardIndex(0);
      setFlashcardDisplayMode("card");
      setFlippedCards({});
      setNotice(response.cards.length ? "Showing past flashcards." : "No saved flashcards yet.");
    } catch {
      setNotice("Could not load past flashcards.");
    } finally {
      setBusy("");
    }
  }

  async function showSavedQuizzes() {
    if (!token) return;
    setPracticeMode("quiz");
    setPracticeSection("quiz");
    setPracticePanelOpen(true);
    setBusy("quiz-history");
    try {
      const response = await apiGet<Quiz[]>("/api/quizzes", token);
      setSavedQuizzes(response);
      setQuiz(response[0] ?? null);
      setCurrentQuizQuestionIndex(0);
      setQuizDisplayMode("list");
      setQuizSelections({});
      setNotice(response.length ? "Showing past quiz questions." : "No saved quizzes yet.");
    } catch {
      setNotice("Could not load past quizzes.");
    } finally {
      setBusy("");
    }
  }

  async function reviewFlashcard(card: Flashcard, rating: "again" | "hard" | "good" | "easy") {
    if (!token || !card.id) return;
    const key = flashcardKey(card);
    try {
      const updated = await apiPost<Flashcard>(`/api/flashcards/${card.id}/review`, { rating }, token);
      setSavedFlashcards((current) => current.map((item) => (flashcardKey(item) === key ? updated : item)));
      setCards((current) => (
        flashcardView === "saved"
          ? current.map((item) => (flashcardKey(item) === key ? updated : item))
          : current.filter((item) => flashcardKey(item) !== key)
      ));
      setFlippedCards((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      setNotice(rating === "again" ? "Card will come back soon." : "Card scheduled for a later review.");
    } catch {
      setNotice("Flashcard review needs the backend database running.");
    }
  }

  async function inspectRag() {
    if (!ENABLE_DEV_RAG) return;
    if (!token) {
      setNotice("Sign in before opening the RAG inspector.");
      return;
    }
    setBusy("dev");
    try {
      const response = await apiGet<{ retrieved_chunks: RetrievedChunk[] }>(
        `/api/dev/rag?question=${encodeURIComponent(question)}`,
        token
      );
      setDevChunks(response.retrieved_chunks);
    } catch {
      setDevChunks([]);
      setNotice("RAG inspection needs indexed documents in the backend.");
    } finally {
      setBusy("");
    }
  }

  function openPractice(section: "focus" | "flashcards" | "quiz" | "weak") {
    setPracticeSection(section);
    if (section === "flashcards") setPracticeMode("flashcards");
    if (section === "quiz") setPracticeMode("quiz");
    setPracticePanelOpen(true);
  }

  function renderChatAnswer() {
    if (busy === "chat") {
      return (
        <div className="mt-6 rounded-lg border border-blue-900/70 bg-slate-950/75 p-4">
          <div className="mb-3 flex items-center justify-between gap-3 text-sm">
            <span className="font-medium text-blue-100">Cramly is reading and writing your answer</span>
            <span className="text-slate-400">Usually a few seconds</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-800">
            <div className="loading-bar-fill h-full rounded-full bg-blue-400 shadow-[0_0_18px_rgba(96,165,250,0.8)]" />
          </div>
        </div>
      );
    }
    if (!chat) return null;
    return (
      <div className="mt-6 rounded-lg border border-blue-900/70 bg-slate-950/75 p-5 text-left">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-blue-600/20 px-3 py-1 text-sm font-medium text-blue-100 ring-1 ring-blue-500/30">
            {sourceText}
          </span>
          <span className="rounded-full bg-slate-900 px-3 py-1 text-sm text-slate-300 ring-1 ring-slate-700">
            {depthText}
          </span>
        </div>
        <StudyAnswer answer={chat.answer} sourceLabel={chat.source_label} />
        {chat.citations.length ? (
          <div className="mt-5 border-t border-slate-800 pt-4">
            <p className="mb-2 text-sm font-semibold text-slate-200">Sources used</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {chat.citations.slice(0, 6).map((citation) => (
                <div key={`${citation.document_name}-${citation.section}-${citation.chunk_id}`} className="rounded-lg bg-slate-900/80 px-3 py-2 text-sm text-slate-300 ring-1 ring-slate-800">
                  <span className="font-medium text-slate-100">{citation.document_name}</span>
                  <span className="text-slate-500"> · </span>
                  <span>{citation.section.replace(/,\s*chunk\s+\d+/i, "")}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function renderMaterialsContent() {
    return (
      <div className="mx-auto mt-7 w-full max-w-[50rem]">
        <label className="focus-ring flex min-h-24 cursor-pointer items-center justify-between gap-4 rounded-[1.25rem] border border-slate-800 bg-slate-950/80 p-4 text-left shadow-[0_0_50px_rgba(37,99,235,0.1)] hover:border-blue-700/70 hover:bg-blue-950/20">
          <span className="flex min-w-0 items-center gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-blue-600/20 text-blue-200 ring-1 ring-blue-500/30">
              <Upload size={22} />
            </span>
            <span className="min-w-0">
              <span className="block font-semibold text-slate-100">{busy === "upload" ? "Indexing..." : "Upload study materials"}</span>
              <span className="mt-1 block truncate text-xs text-slate-400">PDF, DOCX, PPTX, TXT, Markdown, CSV, PNG, JPG, WEBP, TIFF</span>
            </span>
          </span>
          <span className="hidden rounded-lg border border-blue-800/70 bg-blue-950/50 px-3 py-2 text-sm font-medium text-blue-100 sm:inline-flex">
            Choose file
          </span>
          <input
            className="sr-only"
            type="file"
            accept=".txt,.md,.markdown,.csv,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp,.tif,.tiff"
            disabled={busy === "upload"}
            onChange={(event) => {
              uploadFile(event.target.files?.[0]);
              event.currentTarget.value = "";
            }}
          />
        </label>
        {uploadState.fileName ? (
          <div className={`mt-3 rounded-lg border p-4 text-left ${uploadState.error ? "border-red-900/70 bg-red-950/35" : "border-blue-900/70 bg-slate-950/70"}`}>
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-100">{uploadState.fileName}</p>
                <p className={`mt-1 text-sm ${uploadState.error ? "text-red-100" : "text-slate-400"}`}>
                  {uploadState.error || (uploadState.done ? "Indexed and ready for questions." : uploadSteps[uploadState.step])}
                </p>
              </div>
              {uploadState.error ? (
                <XCircle className="shrink-0 text-red-300" size={20} />
              ) : uploadState.done ? (
                <CheckCircle2 className="shrink-0 text-blue-300" size={20} />
              ) : null}
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full transition-all duration-500 ${uploadState.error ? "bg-red-400" : "bg-blue-400"}`}
                style={{ width: `${uploadProgressPercent}%` }}
              />
            </div>
          </div>
        ) : null}
        <details className="mt-3 rounded-[1.25rem] border border-slate-800 bg-slate-950/70 p-4 text-left">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold text-slate-200">
            <span className="inline-flex items-center gap-2">
              <FileText className="text-blue-300" size={17} />
              Uploaded materials
            </span>
            <span className="rounded-full bg-blue-600/20 px-2.5 py-1 text-xs text-blue-100 ring-1 ring-blue-500/30">
              {documents.length}
            </span>
          </summary>
          <div className="mt-4 max-h-72 space-y-3 overflow-y-auto pr-1">
            {documents.map((document) => (
              <div key={document.id} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{document.name}</p>
                    <p className="mt-1 text-sm text-slate-400">{document.chunks} indexed chunks</p>
                    {document.keywords.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {document.keywords.slice(0, 4).map((keyword) => (
                          <span key={keyword} className="rounded-full bg-slate-800 px-2 py-1 text-xs text-slate-300">
                            {keyword}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="rounded-full bg-blue-600/20 px-2 py-1 text-xs font-medium text-blue-100 ring-1 ring-blue-500/30">{document.status}</span>
                    <button
                      type="button"
                      onClick={() => deleteDocument(document)}
                      disabled={busy === `delete-document-${document.id}`}
                      className={`focus-ring inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs font-medium ${
                        confirmingDocumentId === document.id
                          ? "border-red-500/70 bg-red-950/50 text-red-100 hover:border-red-300"
                          : "border-slate-700 bg-slate-950 text-slate-300 hover:border-red-500/70 hover:text-red-100"
                      } disabled:cursor-not-allowed disabled:opacity-70`}
                    >
                      <Trash2 size={13} /> {confirmingDocumentId === document.id ? "Confirm" : "Delete"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {!documents.length ? (
              <p className="rounded-lg bg-slate-900/80 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
                Uploaded materials will appear here.
              </p>
            ) : null}
          </div>
        </details>
      </div>
    );
  }

  function renderFocusContent() {
    return (
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="rounded-full bg-blue-600/20 px-3 py-1 text-sm font-medium text-blue-100 ring-1 ring-blue-500/30">
            {plan.focus_topics[0]}
          </span>
          <button
            type="button"
            onClick={generateStudyPlan}
            disabled={busy === "study-plan"}
            className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {busy === "study-plan" ? "Generating..." : plan.id ? "Refresh plan" : "Generate plan"}
          </button>
        </div>
        {plan.plan.map((item) => (
          <div key={item} className="flex gap-3 rounded-lg bg-slate-950/70 p-3 ring-1 ring-slate-800">
            <CheckCircle2 className="mt-0.5 shrink-0 text-blue-400" size={18} />
            <p className="text-sm leading-6 text-slate-300">{item}</p>
          </div>
        ))}
      </div>
    );
  }

  function renderWeakContent() {
    return (
      <div className="grid gap-3">
        {weakTopics.map((topic) => (
          <div key={topic.topic} className="rounded-lg bg-blue-950/35 p-3 ring-1 ring-blue-800/60">
            <div className="flex items-center justify-between gap-2">
              <p className="font-semibold text-blue-100">{topic.topic}</p>
              <span className="text-sm text-blue-200">{Math.round(topic.accuracy * 100)}%</span>
            </div>
            <p className="mt-2 text-sm leading-6 text-blue-200/90">{topic.recommendation}</p>
          </div>
        ))}
        {!weakTopics.length ? (
          <p className="rounded-lg bg-slate-950/70 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
            Missed quiz topics will shape your study plan.
          </p>
        ) : null}
      </div>
    );
  }

  function renderFlashcardContent() {
    return (
      <>
        <div className="mb-4 flex flex-wrap gap-2">
          <button onClick={generateFlashcards} className="focus-ring rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500">
            New flashcards
          </button>
          <button onClick={showDueFlashcards} className={`focus-ring rounded-lg border px-3 py-2 text-sm font-medium ${flashcardView === "due" ? "border-blue-500 bg-blue-600/20 text-blue-100" : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"}`}>
            Due today
          </button>
          <button onClick={showSavedFlashcards} className={`focus-ring rounded-lg border px-3 py-2 text-sm font-medium ${flashcardView === "saved" ? "border-blue-500 bg-blue-600/20 text-blue-100" : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"}`}>
            Past flashcards {savedFlashcards.length ? `(${savedFlashcards.length})` : ""}
          </button>
          <button
            type="button"
            onClick={() => setFlashcardDisplayMode((current) => (current === "card" ? "list" : "card"))}
            disabled={!cards.length}
            className={`focus-ring inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${
              flashcardDisplayMode === "list"
                ? "border-blue-500 bg-blue-600/20 text-blue-100"
                : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <List size={16} /> {flashcardDisplayMode === "card" ? "List" : "Study one card"}
          </button>
        </div>
        <div className="grid gap-3">
          {flashcardDisplayMode === "card" && currentFlashcard ? (() => {
            const key = flashcardKey(currentFlashcard);
            const flipped = Boolean(flippedCards[key]);
            return (
              <div className="rounded-lg bg-blue-950/35 p-4 ring-1 ring-blue-800/60">
                <div className="mb-2 flex items-center justify-between gap-2 text-xs text-blue-200/80">
                  <span>{currentFlashcard.topic}</span>
                  <span>{formatSavedDate(currentFlashcard.created_at)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setFlippedCards((current) => ({ ...current, [key]: !current[key] }))}
                  className="focus-ring min-h-56 w-full rounded-lg border border-blue-800/70 bg-slate-950/70 p-5 text-left transition hover:border-blue-400"
                >
                  <span className="text-xs font-semibold uppercase text-blue-300">
                    {flipped ? "Answer" : "Prompt"}
                  </span>
                  <span className="mt-4 block text-xl font-semibold leading-8 text-blue-50">
                    {flipped ? currentFlashcard.answer : currentFlashcard.question}
                  </span>
                  <span className="mt-5 block text-sm text-blue-200/80">
                    {flipped ? "Choose how well you knew it." : "Tap to flip"}
                  </span>
                </button>
                {flipped ? (
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {(["again", "hard", "good", "easy"] as const).map((rating) => (
                      <button
                        key={rating}
                        type="button"
                        onClick={() => reviewFlashcard(currentFlashcard, rating)}
                        disabled={!currentFlashcard.id}
                        className="focus-ring rounded-lg border border-blue-800/70 bg-slate-950 px-3 py-2 text-sm font-medium capitalize text-blue-100 hover:border-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {rating}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="mt-4 flex items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => setCurrentFlashcardIndex(Math.max(0, activeFlashcardIndex - 1))}
                    disabled={activeFlashcardIndex === 0}
                    className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    <ChevronLeft size={16} /> Previous
                  </button>
                  <span className="shrink-0 text-sm font-medium text-blue-100">
                    {currentFlashcardNumber} of {cards.length}
                  </span>
                  <button
                    type="button"
                    onClick={() => setCurrentFlashcardIndex(Math.min(cards.length - 1, activeFlashcardIndex + 1))}
                    disabled={activeFlashcardIndex >= cards.length - 1}
                    className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    Next <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            );
          })() : null}
          {flashcardDisplayMode === "list" && cards.length ? (
            <div className="max-h-[34rem] space-y-3 overflow-y-auto pr-1">
              {cards.map((card) => {
                const key = flashcardKey(card);
                const flipped = Boolean(flippedCards[key]);
                return (
                  <div key={key} className="rounded-lg bg-blue-950/35 p-4 ring-1 ring-blue-800/60">
                    <button
                      type="button"
                      onClick={() => setFlippedCards((current) => ({ ...current, [key]: !current[key] }))}
                      className="focus-ring min-h-36 w-full rounded-lg border border-blue-800/70 bg-slate-950/70 p-4 text-left transition hover:border-blue-400"
                    >
                      <span className="text-xs font-semibold uppercase text-blue-300">
                        {flipped ? "Answer" : "Prompt"}
                      </span>
                      <span className="mt-3 block text-lg font-semibold leading-7 text-blue-50">
                        {flipped ? card.answer : card.question}
                      </span>
                    </button>
                  </div>
                );
              })}
            </div>
          ) : null}
          {!cards.length ? (
            <p className="rounded-lg bg-slate-950/70 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
              {flashcardView === "saved" ? "Past flashcards will appear here after you generate them." : "No flashcards are due. Generate new ones or open past flashcards."}
            </p>
          ) : null}
        </div>
      </>
    );
  }

  function renderQuizContent() {
    return (
      <>
        <div className="mb-4 flex flex-wrap gap-2">
          <button onClick={generateQuiz} className="focus-ring rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500">
            New quiz
          </button>
          <button onClick={showSavedQuizzes} className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500">
            Past quizzes {savedQuizzes.length ? `(${savedQuizzes.length})` : ""}
          </button>
          <button
            type="button"
            onClick={() => setQuizDisplayMode((current) => (current === "question" ? "list" : "question"))}
            disabled={!quiz && !savedQuizzes.length}
            className={`focus-ring inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${
              quizDisplayMode === "list"
                ? "border-blue-500 bg-blue-600/20 text-blue-100"
                : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <List size={16} /> {quizDisplayMode === "question" ? "List" : "Study one question"}
          </button>
        </div>
        <div className="grid gap-3">
          {quizDisplayMode === "question" && currentQuizQuestion ? (() => {
            const selected = quizSelections[currentQuizQuestion.id];
            const answered = Boolean(selected);
            const correct = selected === currentQuizQuestion.answer;
            return (
              <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase text-blue-300">
                      Question {currentQuizQuestionNumber} of {quizQuestions.length}
                    </p>
                    <p className="font-semibold leading-7">{currentQuizQuestion.prompt}</p>
                  </div>
                  {answered ? (
                    correct ? (
                      <CheckCircle2 className="mt-1 shrink-0 text-blue-300" size={18} />
                    ) : (
                      <XCircle className="mt-1 shrink-0 text-red-300" size={18} />
                    )
                  ) : null}
                </div>
                <div className="grid gap-2">
                  {currentQuizQuestion.choices.map((choice) => {
                    const isSelected = selected === choice;
                    const isAnswer = answered && choice === currentQuizQuestion.answer;
                    const isWrongSelection = answered && isSelected && !isAnswer;
                    return (
                      <button
                        key={choice}
                        type="button"
                        onClick={() => chooseQuizAnswer(currentQuizQuestion, choice)}
                        disabled={answered}
                        className={`focus-ring rounded-lg border px-3 py-3 text-left text-sm leading-6 transition disabled:cursor-default ${
                          isAnswer
                            ? "border-blue-400 bg-blue-600/25 text-blue-50"
                            : isWrongSelection
                              ? "border-red-400/70 bg-red-950/40 text-red-50"
                              : "border-slate-800 bg-slate-900/80 text-slate-300 hover:border-blue-500"
                        }`}
                      >
                        {choice}
                      </button>
                    );
                  })}
                </div>
                {answered ? (
                  <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/80 p-3 text-sm leading-6 text-slate-300">
                    <p className={correct ? "font-semibold text-blue-100" : "font-semibold text-red-100"}>
                      {correct ? "Correct" : "Not quite"}
                    </p>
                    {!correct ? <p className="mt-1">Correct answer: {currentQuizQuestion.answer}</p> : null}
                    <p className="mt-2">{currentQuizQuestion.explanation}</p>
                  </div>
                ) : null}
                <div className="mt-4 flex items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => setCurrentQuizQuestionIndex(Math.max(0, activeQuizQuestionIndex - 1))}
                    disabled={activeQuizQuestionIndex === 0}
                    className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    <ChevronLeft size={16} /> Previous
                  </button>
                  <span className="shrink-0 text-sm font-medium text-blue-100">
                    {currentQuizQuestionNumber} of {quizQuestions.length}
                  </span>
                  <button
                    type="button"
                    onClick={() => setCurrentQuizQuestionIndex(Math.min(quizQuestions.length - 1, activeQuizQuestionIndex + 1))}
                    disabled={activeQuizQuestionIndex >= quizQuestions.length - 1}
                    className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    Next <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            );
          })() : null}
          {quizDisplayMode === "list" && savedQuizzes.length ? (
            <div className="max-h-[34rem] space-y-3 overflow-y-auto pr-1">
              {savedQuizzes.map((savedQuiz, index) => (
                <div
                  key={savedQuiz.id}
                  className={`rounded-lg border p-4 ${
                    quiz?.id === savedQuiz.id
                      ? "border-blue-700/70 bg-blue-950/35"
                      : "border-slate-800 bg-slate-950/50"
                  }`}
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-slate-100">Quiz {savedQuizzes.length - index}</p>
                      <p className="mt-1 text-sm text-slate-400">
                        {savedQuiz.questions.length} questions · {formatSavedDate(savedQuiz.created_at)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setQuiz(savedQuiz);
                        setCurrentQuizQuestionIndex(0);
                        setQuizDisplayMode("question");
                        setQuizSelections({});
                      }}
                      className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500"
                    >
                      Study
                    </button>
                  </div>
                  <div className="grid gap-2">
                    {savedQuiz.questions.slice(0, 3).map((questionItem, questionIndex) => (
                      <p key={questionItem.id} className="rounded-lg bg-slate-900/80 px-3 py-2 text-sm leading-6 text-slate-300 ring-1 ring-slate-800">
                        {questionIndex + 1}. {questionItem.prompt}
                      </p>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {!quiz ? (
            <p className="rounded-lg bg-slate-950/70 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
              Generate a quiz or open past quizzes.
            </p>
          ) : null}
        </div>
      </>
    );
  }

  function renderPracticeContent() {
    if (practiceSection === "flashcards") return renderFlashcardContent();
    if (practiceSection === "quiz") return renderQuizContent();
    if (practiceSection === "weak") return renderWeakContent();
    return renderFocusContent();
  }

  if (!showDashboard) {
    return (
      <main className="relative grid min-h-screen place-items-center overflow-hidden bg-[#050914] px-5 text-slate-100">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(59,130,246,0.075)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.075)_1px,transparent_1px)] bg-[size:48px_48px]" />
        <div className="absolute left-1/2 top-1/2 h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-600/20 blur-3xl" />
        <div className="absolute left-1/2 top-24 h-72 w-72 -translate-x-1/2 rounded-full bg-blue-400/10 blur-3xl" />

        <section className="relative z-10 flex w-full max-w-3xl flex-col items-center text-center">
          <div className="relative mb-8 h-56 w-56 overflow-hidden rounded-[2rem] border border-blue-500/50 bg-slate-950 shadow-[0_0_90px_rgba(37,99,235,0.5)] sm:h-72 sm:w-72">
            <Image
              src="/cramly-logo.png"
              alt="Cramly logo"
              fill
              priority
              sizes="(max-width: 640px) 224px, 288px"
              className="object-cover"
            />
          </div>
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.28em] text-blue-300">Cramly</p>
          <h1 className="text-4xl font-semibold leading-tight text-slate-50 sm:text-5xl">
            Studying, enhanced by AI
          </h1>
          <p className="mt-4 max-w-xl text-base leading-7 text-slate-400 sm:text-lg">
            Turn notes, lectures, PDFs, flashcards, and quizzes into one focused exam prep workspace.
          </p>
          <button
            onClick={() => setShowDashboard(true)}
            className="focus-ring mt-8 min-h-12 rounded-lg bg-blue-600 px-8 py-3 text-base font-semibold text-white shadow-[0_0_40px_rgba(37,99,235,0.45)] transition hover:bg-blue-500"
          >
            Open Study Dashboard
          </button>
        </section>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="relative grid min-h-screen place-items-center overflow-hidden bg-[#050914] px-5 py-10 text-slate-100">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(59,130,246,0.075)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.075)_1px,transparent_1px)] bg-[size:48px_48px]" />
        <div className="absolute left-1/2 top-1/2 h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-600/20 blur-3xl" />

        <section className="relative z-10 grid w-full max-w-5xl gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="flex flex-col justify-center">
            <div className="relative mb-6 h-24 w-24 overflow-hidden rounded-2xl border border-blue-500/50 bg-slate-950 shadow-[0_0_50px_rgba(37,99,235,0.45)]">
              <Image
                src="/cramly-logo.png"
                alt="Cramly logo"
                fill
                priority
                sizes="96px"
                className="object-cover"
              />
            </div>
            <p className="mb-3 inline-flex w-fit items-center gap-2 rounded-full bg-blue-600/20 px-3 py-1 text-sm font-medium text-blue-100 ring-1 ring-blue-500/30">
              <Shield size={16} /> Private study workspace
            </p>
            <h1 className="text-4xl font-semibold leading-tight text-slate-50 sm:text-5xl">
              Your notes, quizzes, and weak spots stay with your account.
            </h1>
            <p className="mt-4 max-w-xl text-base leading-7 text-slate-400">
              Sign in to upload class materials, ask source-cited questions, and keep your study history separated from everyone else.
            </p>
          </div>

          <form onSubmit={submitAuth} className="rounded-lg border border-slate-800 bg-slate-950/85 p-6 shadow-[0_0_80px_rgba(37,99,235,0.2)]">
            <div className="mb-6 flex items-center justify-between gap-4">
              <div>
                <p className="flex items-center gap-2 text-xl font-semibold">
                  <UserRound size={22} /> {authMode === "login" ? "Sign in" : "Create account"}
                </p>
                <p className="mt-1 text-sm text-slate-400">Use your email and a password with at least 8 characters.</p>
              </div>
              <div className="flex rounded-lg border border-slate-800 bg-slate-900 p-1">
                <button
                  type="button"
                  onClick={() => setAuthMode("login")}
                  className={`rounded-md px-3 py-2 text-sm font-medium ${authMode === "login" ? "bg-blue-600 text-white" : "text-slate-300 hover:text-white"}`}
                >
                  Login
                </button>
                <button
                  type="button"
                  onClick={() => setAuthMode("register")}
                  className={`rounded-md px-3 py-2 text-sm font-medium ${authMode === "register" ? "bg-blue-600 text-white" : "text-slate-300 hover:text-white"}`}
                >
                  New
                </button>
              </div>
            </div>

            <div className="grid gap-4">
              <label className="grid gap-2 text-sm font-medium text-slate-200">
                Email
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  type="email"
                  autoComplete="email"
                  className="focus-ring min-h-11 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-base text-slate-100 placeholder:text-slate-500"
                  placeholder="you@school.edu"
                  required
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-slate-200">
                Password
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                  autoComplete={authMode === "login" ? "current-password" : "new-password"}
                  minLength={8}
                  className="focus-ring min-h-11 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-base text-slate-100 placeholder:text-slate-500"
                  placeholder="8+ characters"
                  required
                />
              </label>
              {authMode === "register" && REQUIRE_INVITE_CODE ? (
                <label className="grid gap-2 text-sm font-medium text-slate-200">
                  Invite code
                  <input
                    value={inviteCode}
                    onChange={(event) => setInviteCode(event.target.value)}
                    type="text"
                    autoComplete="off"
                    maxLength={128}
                    className="focus-ring min-h-11 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-base text-slate-100 placeholder:text-slate-500"
                    placeholder="Beta invite code"
                    required
                  />
                </label>
              ) : null}
            </div>

            {authError ? (
              <p className="mt-4 rounded-lg border border-red-900/70 bg-red-950/40 px-3 py-2 text-sm text-red-100">
                {authError}
              </p>
            ) : null}

            <button
              disabled={busy === "auth"}
              className="focus-ring mt-6 min-h-12 w-full rounded-lg bg-blue-600 px-5 py-3 text-base font-semibold text-white shadow-[0_0_40px_rgba(37,99,235,0.35)] transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {busy === "auth" ? "Checking..." : authMode === "login" ? "Open My Dashboard" : "Create Private Workspace"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <>
      <main className="relative min-h-screen overflow-hidden bg-[#050914] text-slate-100">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(59,130,246,0.055)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.055)_1px,transparent_1px)] bg-[size:56px_56px]" />
        <div className="relative z-10 flex min-h-screen flex-col">
          <header className="flex items-center justify-between gap-4 px-5 py-4">
            <button
              type="button"
              onClick={() => setShowDashboard(true)}
              className="focus-ring relative h-10 w-10 overflow-hidden rounded-lg border border-blue-500/50 bg-slate-950 shadow-lg shadow-blue-950/40"
              aria-label="Cramly home"
            >
              <Image
                src="/cramly-logo.png"
                alt="Cramly logo"
                fill
                priority
                sizes="40px"
                className="object-cover"
              />
            </button>

            <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
              <button
                type="button"
                onClick={() => openPractice("focus")}
                className="focus-ring inline-flex items-center gap-2 rounded-lg border border-blue-700/70 bg-blue-950/70 px-3 py-2 font-semibold text-blue-100 hover:border-blue-400"
              >
                <Brain size={16} /> Practice
              </button>
              <button
                type="button"
                onClick={() => refresh()}
                className="focus-ring rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2 font-medium text-slate-100 hover:border-blue-500"
              >
                Refresh
              </button>
              <button
                type="button"
                onClick={signOut}
                className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2 font-medium text-slate-100 hover:border-blue-500"
              >
                <LogOut size={16} /> Sign out
              </button>
            </div>
          </header>

          <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center px-5 pb-10 pt-4 text-center lg:-mt-12">
            <div className="mb-8 flex items-center justify-center gap-5">
              <div className="relative h-20 w-20 overflow-hidden rounded-[1.35rem] border border-blue-500/50 bg-slate-950 shadow-[0_0_60px_rgba(37,99,235,0.36)] sm:h-24 sm:w-24">
                <Image
                  src="/cramly-logo.png"
                  alt="Cramly logo"
                  fill
                  priority
                  sizes="(max-width: 640px) 80px, 96px"
                  className="object-cover"
                />
              </div>
              <h1 className="text-6xl font-semibold tracking-normal text-slate-50 sm:text-7xl">Cramly</h1>
            </div>

            <form onSubmit={ask} className="w-full max-w-[50rem]">
              <div className="rounded-[1.75rem] border border-slate-800 bg-slate-950/85 p-3 shadow-[0_0_80px_rgba(37,99,235,0.16)]">
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  className="focus-ring min-h-16 w-full resize-none rounded-[1.25rem] border border-slate-800 bg-slate-900/80 px-5 py-4 text-base leading-7 text-slate-100 placeholder:text-slate-500"
                  placeholder="What do you want to study?"
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap gap-2">
                    <select
                      value={mode}
                      onChange={(event) => setMode(event.target.value as typeof mode)}
                      className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                    >
                      <option value="auto">Auto source</option>
                      <option value="materials">Uploaded materials</option>
                      <option value="general">OpenAI general knowledge</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                    <select
                      value={depth}
                      onChange={(event) => setDepth(event.target.value as typeof depth)}
                      className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                    >
                      <option value="standard">Study Mode</option>
                      <option value="advanced">Expert Mode</option>
                    </select>
                  </div>
                  <button
                    disabled={busy === "chat"}
                    className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-blue-800"
                  >
                    <MessageSquare size={18} /> {busy === "chat" ? "Thinking..." : "Ask Cramly"}
                  </button>
                </div>
              </div>
            </form>

            <p className="mt-4 max-w-[50rem] rounded-full border border-blue-900/60 bg-blue-950/40 px-4 py-2 text-sm text-blue-100">
              {notice}
            </p>

            {renderChatAnswer()}
            {renderMaterialsContent()}

            <details className="mx-auto mt-5 w-full max-w-[50rem] rounded-[1.25rem] border border-slate-800 bg-slate-950/60 p-4 text-left">
              <summary className="cursor-pointer text-sm font-semibold text-slate-200">Account safety</summary>
              <form onSubmit={changePassword} className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="grid gap-2 text-sm font-medium text-slate-200">
                  Current password
                  <input
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    type="password"
                    autoComplete="current-password"
                    minLength={8}
                    maxLength={128}
                    className="focus-ring min-h-11 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-base text-slate-100 placeholder:text-slate-500"
                    placeholder="Current password"
                    required
                  />
                </label>
                <label className="grid gap-2 text-sm font-medium text-slate-200">
                  New password
                  <input
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    maxLength={128}
                    className="focus-ring min-h-11 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-base text-slate-100 placeholder:text-slate-500"
                    placeholder="8+ characters"
                    required
                  />
                </label>
                <button
                  disabled={busy === "password"}
                  className="focus-ring inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-70 sm:col-span-2"
                >
                  <KeyRound size={17} /> {busy === "password" ? "Updating..." : "Change password"}
                </button>
              </form>
              <div className="mt-5 grid gap-3 border-t border-slate-800 pt-5 sm:grid-cols-[1fr_auto]">
                <input
                  value={accountDeleteConfirmation}
                  onChange={(event) => setAccountDeleteConfirmation(event.target.value)}
                  type="text"
                  autoComplete="off"
                  className="focus-ring min-h-11 rounded-lg border border-red-900/70 bg-red-950/30 px-3 py-2 text-base text-red-50 placeholder:text-red-200/50"
                  placeholder="Type DELETE"
                />
                <button
                  type="button"
                  onClick={deleteAccount}
                  disabled={accountDeleteConfirmation !== "DELETE" || busy === "account-delete"}
                  className="focus-ring inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-red-800 bg-red-950/70 px-4 py-2 font-semibold text-red-50 hover:border-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Trash2 size={17} /> {busy === "account-delete" ? "Deleting..." : "Delete account"}
                </button>
              </div>
            </details>
          </section>
        </div>

        {practicePanelOpen ? (
          <aside className="fixed right-4 top-20 z-40 max-h-[calc(100vh-6rem)] w-[min(94vw,36rem)] overflow-y-auto rounded-lg border border-slate-800 bg-slate-900/95 p-5 shadow-[0_0_80px_rgba(2,6,23,0.7)] backdrop-blur">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Brain className="text-blue-300" size={20} /> Practice
              </h2>
              <button
                type="button"
                onClick={() => setPracticePanelOpen(false)}
                className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500"
              >
                Close
              </button>
            </div>
            <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {([
                ["focus", "Focus", Target],
                ["flashcards", "Flashcards", Layers3],
                ["quiz", "Quiz", Brain],
                ["weak", "Weak", BookOpen]
              ] as const).map(([section, label, Icon]) => (
                <button
                  key={section}
                  type="button"
                  onClick={() => openPractice(section)}
                  className={`focus-ring inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${
                    practiceSection === section
                      ? "border-blue-500 bg-blue-600/20 text-blue-100"
                      : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"
                  }`}
                >
                  <Icon size={15} /> {label}
                </button>
              ))}
            </div>
            {renderPracticeContent()}
            {ENABLE_DEV_RAG ? (
              <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950/70 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <p className="flex items-center gap-2 text-sm font-semibold">
                    <Activity className="text-blue-300" size={16} /> Dev RAG
                  </p>
                  <button onClick={inspectRag} className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500">
                    Inspect
                  </button>
                </div>
                <div className="grid gap-3">
                  {devChunks.map((chunk) => (
                    <div key={chunk.id} className="rounded-lg bg-slate-900 p-3 text-white ring-1 ring-blue-900/70">
                      <p className="text-sm font-semibold">{chunk.document_name} · {chunk.section} · {chunk.score.toFixed(2)}</p>
                      <p className="mt-2 line-clamp-4 text-sm leading-6 text-slate-200">{chunk.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </aside>
        ) : null}
      </main>

      <div className="hidden" aria-hidden="true">
        <main className="min-h-screen bg-[#0b1120] text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/85">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="relative h-12 w-12 overflow-hidden rounded-lg border border-blue-500/60 bg-slate-950 shadow-lg shadow-blue-950/40">
              <Image
                src="/cramly-logo.png"
                alt="Cramly logo"
                fill
                priority
                sizes="48px"
                className="object-cover"
              />
            </div>
            <div>
              <p className="text-xl font-semibold">Cramly</p>
              <p className="text-sm text-slate-400">AI learning companion</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-slate-200">
              <UserRound size={15} /> {user.email}
            </span>
            <span className="rounded-full border border-blue-700/70 bg-blue-950/70 px-3 py-1 text-blue-100">{notice}</span>
            <button onClick={() => refresh()} className="focus-ring rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-medium text-slate-100 hover:border-blue-500">
              Refresh
            </button>
            <button onClick={signOut} className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-medium text-slate-100 hover:border-blue-500">
              <LogOut size={16} /> Sign out
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-5 shadow-soft">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="mb-2 inline-flex items-center gap-2 rounded-full bg-blue-600/20 px-3 py-1 text-sm font-medium text-blue-200 ring-1 ring-blue-500/30">
                <Sparkles size={16} /> Exam mode
              </p>
              <h1 className="max-w-2xl text-4xl font-semibold leading-tight text-slate-50">
                Turn messy class material into a focused study session.
              </h1>
            </div>
            <div className="rounded-lg border border-slate-700 bg-slate-950/70 p-4">
              <p className="text-sm text-slate-400">Answer source</p>
              <p className="mt-1 font-semibold text-blue-100">{sourceText}</p>
            </div>
          </div>

          <form onSubmit={ask} className="grid gap-3">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              className="focus-ring min-h-28 resize-none rounded-lg border border-slate-700 bg-slate-950/70 p-4 text-base text-slate-100 placeholder:text-slate-500"
              placeholder="Ask about your notes or any study concept"
            />
            <div className="flex flex-wrap gap-3">
              <select
                value={mode}
                onChange={(event) => setMode(event.target.value as typeof mode)}
                className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
              >
                <option value="auto">Auto source</option>
                <option value="materials">Uploaded materials</option>
                <option value="general">OpenAI general knowledge</option>
                <option value="hybrid">Hybrid</option>
              </select>
              <select
                value={depth}
                onChange={(event) => setDepth(event.target.value as typeof depth)}
                className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
              >
                <option value="standard">Study Mode</option>
                <option value="advanced">Expert Mode</option>
              </select>
              <button
                disabled={busy === "chat"}
                className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500 disabled:bg-blue-800"
              >
                <MessageSquare size={18} /> {busy === "chat" ? "Thinking..." : "Ask Cramly"}
              </button>
            </div>
          </form>

          {busy === "chat" ? (
            <div className="mt-5 rounded-lg border border-blue-900/70 bg-slate-950/75 p-4">
              <div className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-blue-100">Cramly is reading and writing your answer</span>
                <span className="text-slate-400">Usually a few seconds</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                <div className="loading-bar-fill h-full rounded-full bg-blue-400 shadow-[0_0_18px_rgba(96,165,250,0.8)]" />
              </div>
            </div>
          ) : null}

          {chat ? (
            <div className="mt-5 rounded-lg border border-blue-900/70 bg-slate-950/75 p-5">
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-blue-600/20 px-3 py-1 text-sm font-medium text-blue-100 ring-1 ring-blue-500/30">
                  {sourceText}
                </span>
                <span className="rounded-full bg-slate-900 px-3 py-1 text-sm text-slate-300 ring-1 ring-slate-700">
                  {depthText}
                </span>
              </div>
              <StudyAnswer answer={chat.answer} sourceLabel={chat.source_label} />
              {chat.citations.length ? (
                <div className="mt-5 border-t border-slate-800 pt-4">
                  <p className="mb-2 text-sm font-semibold text-slate-200">Sources used</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {chat.citations.slice(0, 6).map((citation) => (
                      <div key={`${citation.document_name}-${citation.section}-${citation.chunk_id}`} className="rounded-lg bg-slate-900/80 px-3 py-2 text-sm text-slate-300 ring-1 ring-slate-800">
                        <span className="font-medium text-slate-100">{citation.document_name}</span>
                        <span className="text-slate-500"> · </span>
                        <span>{citation.section.replace(/,\s*chunk\s+\d+/i, "")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <aside className="rounded-lg border border-slate-800 bg-slate-900/90 p-5 shadow-soft">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Target size={20} /> Today&apos;s focus
            </h2>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={generateStudyPlan}
                disabled={busy === "study-plan"}
                className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {busy === "study-plan" ? "Generating..." : plan.id ? "Refresh plan" : "Generate plan"}
              </button>
              <span className="rounded-full bg-blue-600/20 px-3 py-1 text-sm font-medium text-blue-100 ring-1 ring-blue-500/30">
                {plan.focus_topics[0]}
              </span>
            </div>
          </div>
          <div className="grid gap-3">
            {plan.plan.map((item) => (
              <div key={item} className="flex gap-3 rounded-lg bg-slate-950/70 p-3 ring-1 ring-slate-800">
                <CheckCircle2 className="mt-0.5 shrink-0 text-blue-400" size={18} />
                <p className="text-sm leading-6 text-slate-300">{item}</p>
              </div>
            ))}
          </div>
        </aside>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 pb-8 lg:grid-cols-3">
        <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-5">
          <div className="mb-4 flex items-center gap-2">
            <Upload className="text-blue-300" size={20} />
            <h2 className="text-lg font-semibold">Materials</h2>
          </div>
          <label className="focus-ring flex min-h-36 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-blue-700/60 bg-blue-950/20 p-5 text-center hover:bg-blue-950/35">
            <FileText className="text-blue-300" size={28} />
            <span className="font-medium text-slate-100">{busy === "upload" ? "Indexing..." : "Upload notes, PDFs, docs, slides, images"}</span>
            <span className="text-xs text-slate-400">PDF, DOCX, PPTX, TXT, Markdown, CSV, PNG, JPG, WEBP, TIFF</span>
            <input
              className="sr-only"
              type="file"
              accept=".txt,.md,.markdown,.csv,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp,.tif,.tiff"
              disabled={busy === "upload"}
              onChange={(event) => {
                uploadFile(event.target.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
          </label>
          {uploadState.fileName ? (
            <div className={`mt-4 rounded-lg border p-4 ${uploadState.error ? "border-red-900/70 bg-red-950/35" : "border-blue-900/70 bg-slate-950/70"}`}>
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-slate-100">{uploadState.fileName}</p>
                  <p className={`mt-1 text-sm ${uploadState.error ? "text-red-100" : "text-slate-400"}`}>
                    {uploadState.error || (uploadState.done ? "Indexed and ready for questions." : uploadSteps[uploadState.step])}
                  </p>
                </div>
                {uploadState.error ? (
                  <XCircle className="shrink-0 text-red-300" size={20} />
                ) : uploadState.done ? (
                  <CheckCircle2 className="shrink-0 text-blue-300" size={20} />
                ) : null}
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${uploadState.error ? "bg-red-400" : "bg-blue-400"}`}
                  style={{ width: `${uploadProgressPercent}%` }}
                />
              </div>
              <div className="mt-3 grid gap-2">
                {uploadSteps.map((step, index) => {
                  const complete = uploadState.done || index < uploadState.step;
                  const active = !uploadState.done && !uploadState.error && index === uploadState.step;
                  return (
                    <div key={step} className="flex items-center gap-2 text-xs text-slate-400">
                      <span className={`h-2 w-2 rounded-full ${complete ? "bg-blue-300" : active ? "bg-blue-500" : uploadState.error && index === uploadState.step ? "bg-red-300" : "bg-slate-700"}`} />
                      <span className={active ? "font-medium text-blue-100" : complete ? "text-slate-200" : ""}>{step}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
          <div className="mt-4 grid gap-3">
            {documents.map((document) => (
              <div key={document.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{document.name}</p>
                    <p className="mt-1 text-sm text-slate-400">{document.chunks} indexed chunks</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="rounded-full bg-blue-600/20 px-2 py-1 text-xs font-medium text-blue-100 ring-1 ring-blue-500/30">{document.status}</span>
                    <button
                      type="button"
                      onClick={() => deleteDocument(document)}
                      disabled={busy === `delete-document-${document.id}`}
                      className={`focus-ring inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs font-medium ${
                        confirmingDocumentId === document.id
                          ? "border-red-500/70 bg-red-950/50 text-red-100 hover:border-red-300"
                          : "border-slate-700 bg-slate-900 text-slate-300 hover:border-red-500/70 hover:text-red-100"
                      } disabled:cursor-not-allowed disabled:opacity-70`}
                    >
                      <Trash2 size={13} /> {confirmingDocumentId === document.id ? "Confirm" : "Delete"}
                    </button>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {document.keywords.slice(0, 4).map((keyword) => (
                    <span key={keyword} className="rounded-full bg-slate-800 px-2 py-1 text-xs text-slate-300">
                      {keyword}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Brain className="text-blue-300" size={20} /> Practice
            </h2>
            <div className="flex rounded-lg border border-slate-800 bg-slate-950 p-1">
              <button
                type="button"
                onClick={() => setPracticeMode("flashcards")}
                className={`focus-ring rounded-md px-3 py-2 text-sm font-medium ${practiceMode === "flashcards" ? "bg-blue-600 text-white" : "text-slate-300 hover:text-white"}`}
              >
                Flashcards
              </button>
              <button
                type="button"
                onClick={() => setPracticeMode("quiz")}
                className={`focus-ring rounded-md px-3 py-2 text-sm font-medium ${practiceMode === "quiz" ? "bg-blue-600 text-white" : "text-slate-300 hover:text-white"}`}
              >
                Quiz
              </button>
            </div>
          </div>
          {practiceMode === "flashcards" ? (
            <>
              <div className="mb-4 flex flex-wrap gap-2">
                <button onClick={generateFlashcards} className="focus-ring rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500">
                  New flashcards
                </button>
                <button onClick={showDueFlashcards} className={`focus-ring rounded-lg border px-3 py-2 text-sm font-medium ${flashcardView === "due" ? "border-blue-500 bg-blue-600/20 text-blue-100" : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"}`}>
                  Due today
                </button>
                <button onClick={showSavedFlashcards} className={`focus-ring rounded-lg border px-3 py-2 text-sm font-medium ${flashcardView === "saved" ? "border-blue-500 bg-blue-600/20 text-blue-100" : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"}`}>
                  Past flashcards {savedFlashcards.length ? `(${savedFlashcards.length})` : ""}
                </button>
                <button
                  type="button"
                  onClick={() => setFlashcardDisplayMode((current) => (current === "card" ? "list" : "card"))}
                  disabled={!cards.length}
                  className={`focus-ring inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${
                    flashcardDisplayMode === "list"
                      ? "border-blue-500 bg-blue-600/20 text-blue-100"
                      : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  <List size={16} /> {flashcardDisplayMode === "card" ? "List" : "Study one card"}
                </button>
              </div>
              <div className="grid gap-3">
                {flashcardDisplayMode === "card" && currentFlashcard ? (() => {
                  const key = flashcardKey(currentFlashcard);
                  const flipped = Boolean(flippedCards[key]);
                  return (
                    <div className="rounded-lg bg-blue-950/35 p-4 ring-1 ring-blue-800/60">
                      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-blue-200/80">
                        <span>{currentFlashcard.topic}</span>
                        <span>{formatSavedDate(currentFlashcard.created_at)}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setFlippedCards((current) => ({ ...current, [key]: !current[key] }))}
                        className="focus-ring min-h-56 w-full rounded-lg border border-blue-800/70 bg-slate-950/70 p-5 text-left transition hover:border-blue-400"
                      >
                        <span className="text-xs font-semibold uppercase text-blue-300">
                          {flipped ? "Answer" : "Prompt"}
                        </span>
                        <span className="mt-4 block text-xl font-semibold leading-8 text-blue-50">
                          {flipped ? currentFlashcard.answer : currentFlashcard.question}
                        </span>
                        <span className="mt-5 block text-sm text-blue-200/80">
                          {flipped ? "Choose how well you knew it." : "Tap to flip"}
                        </span>
                      </button>
                      {flipped ? (
                        <div className="mt-3 grid grid-cols-2 gap-2">
                          {(["again", "hard", "good", "easy"] as const).map((rating) => (
                            <button
                              key={rating}
                              type="button"
                              onClick={() => reviewFlashcard(currentFlashcard, rating)}
                              disabled={!currentFlashcard.id}
                              className="focus-ring rounded-lg border border-blue-800/70 bg-slate-950 px-3 py-2 text-sm font-medium capitalize text-blue-100 hover:border-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {rating}
                            </button>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-4 flex items-center justify-between gap-3">
                        <button
                          type="button"
                          onClick={() => setCurrentFlashcardIndex(Math.max(0, activeFlashcardIndex - 1))}
                          disabled={activeFlashcardIndex === 0}
                          className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          <ChevronLeft size={16} /> Previous
                        </button>
                        <span className="shrink-0 text-sm font-medium text-blue-100">
                          {currentFlashcardNumber} of {cards.length}
                        </span>
                        <button
                          type="button"
                          onClick={() => setCurrentFlashcardIndex(Math.min(cards.length - 1, activeFlashcardIndex + 1))}
                          disabled={activeFlashcardIndex >= cards.length - 1}
                          className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          Next <ChevronRight size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })() : null}
                {flashcardDisplayMode === "list" && cards.length ? (
                  <div className="max-h-[34rem] space-y-3 overflow-y-auto pr-1">
                    {cards.map((card) => {
                      const key = flashcardKey(card);
                      const flipped = Boolean(flippedCards[key]);
                      return (
                        <div key={key} className="rounded-lg bg-blue-950/35 p-4 ring-1 ring-blue-800/60">
                          <div className="mb-2 flex items-center justify-between gap-2 text-xs text-blue-200/80">
                            <span>{card.topic}</span>
                            <span>{formatSavedDate(card.created_at)}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => setFlippedCards((current) => ({ ...current, [key]: !current[key] }))}
                            className="focus-ring min-h-36 w-full rounded-lg border border-blue-800/70 bg-slate-950/70 p-4 text-left transition hover:border-blue-400"
                          >
                            <span className="text-xs font-semibold uppercase text-blue-300">
                              {flipped ? "Answer" : "Prompt"}
                            </span>
                            <span className="mt-3 block text-lg font-semibold leading-7 text-blue-50">
                              {flipped ? card.answer : card.question}
                            </span>
                            <span className="mt-4 block text-sm text-blue-200/80">
                              {flipped ? "Choose how well you knew it." : "Tap to flip"}
                            </span>
                          </button>
                          {flipped ? (
                            <div className="mt-3 grid grid-cols-2 gap-2">
                              {(["again", "hard", "good", "easy"] as const).map((rating) => (
                                <button
                                  key={rating}
                                  type="button"
                                  onClick={() => reviewFlashcard(card, rating)}
                                  disabled={!card.id}
                                  className="focus-ring rounded-lg border border-blue-800/70 bg-slate-950 px-3 py-2 text-sm font-medium capitalize text-blue-100 hover:border-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                  {rating}
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                {!cards.length ? (
                  <p className="rounded-lg bg-slate-950/70 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
                    {flashcardView === "saved" ? "Past flashcards will appear here after you generate them." : "No flashcards are due. Generate new ones or open past flashcards."}
                  </p>
                ) : null}
              </div>
            </>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap gap-2">
                <button onClick={generateQuiz} className="focus-ring rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500">
                  New quiz
                </button>
                <button onClick={showSavedQuizzes} className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500">
                  Past quizzes {savedQuizzes.length ? `(${savedQuizzes.length})` : ""}
                </button>
                <button
                  type="button"
                  onClick={() => setQuizDisplayMode((current) => (current === "question" ? "list" : "question"))}
                  disabled={!quiz && !savedQuizzes.length}
                  className={`focus-ring inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${
                    quizDisplayMode === "list"
                      ? "border-blue-500 bg-blue-600/20 text-blue-100"
                      : "border-slate-700 bg-slate-950 text-slate-100 hover:border-blue-500"
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  <List size={16} /> {quizDisplayMode === "question" ? "List" : "Study one question"}
                </button>
              </div>
              <div className="grid gap-3">
                {quizDisplayMode === "question" && currentQuizQuestion ? (() => {
                  const selected = quizSelections[currentQuizQuestion.id];
                  const answered = Boolean(selected);
                  const correct = selected === currentQuizQuestion.answer;
                  return (
                    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <p className="mb-2 text-xs font-semibold uppercase text-blue-300">
                            Question {currentQuizQuestionNumber} of {quizQuestions.length}
                          </p>
                          <p className="font-semibold leading-7">{currentQuizQuestion.prompt}</p>
                        </div>
                        {answered ? (
                          correct ? (
                            <CheckCircle2 className="mt-1 shrink-0 text-blue-300" size={18} />
                          ) : (
                            <XCircle className="mt-1 shrink-0 text-red-300" size={18} />
                          )
                        ) : null}
                      </div>
                      <div className="grid gap-2">
                        {currentQuizQuestion.choices.map((choice) => {
                          const isSelected = selected === choice;
                          const isAnswer = answered && choice === currentQuizQuestion.answer;
                          const isWrongSelection = answered && isSelected && !isAnswer;
                          return (
                            <button
                              key={choice}
                              type="button"
                              onClick={() => chooseQuizAnswer(currentQuizQuestion, choice)}
                              disabled={answered}
                              className={`focus-ring rounded-lg border px-3 py-3 text-left text-sm leading-6 transition disabled:cursor-default ${
                                isAnswer
                                  ? "border-blue-400 bg-blue-600/25 text-blue-50"
                                  : isWrongSelection
                                    ? "border-red-400/70 bg-red-950/40 text-red-50"
                                    : "border-slate-800 bg-slate-900/80 text-slate-300 hover:border-blue-500"
                              }`}
                            >
                              {choice}
                            </button>
                          );
                        })}
                      </div>
                      {answered ? (
                        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/80 p-3 text-sm leading-6 text-slate-300">
                          <p className={correct ? "font-semibold text-blue-100" : "font-semibold text-red-100"}>
                            {correct ? "Correct" : "Not quite"}
                          </p>
                          {!correct ? <p className="mt-1">Correct answer: {currentQuizQuestion.answer}</p> : null}
                          <p className="mt-2">{currentQuizQuestion.explanation}</p>
                        </div>
                      ) : null}
                      <div className="mt-4 flex items-center justify-between gap-3">
                        <button
                          type="button"
                          onClick={() => setCurrentQuizQuestionIndex(Math.max(0, activeQuizQuestionIndex - 1))}
                          disabled={activeQuizQuestionIndex === 0}
                          className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          <ChevronLeft size={16} /> Previous
                        </button>
                        <span className="shrink-0 text-sm font-medium text-blue-100">
                          {currentQuizQuestionNumber} of {quizQuestions.length}
                        </span>
                        <button
                          type="button"
                          onClick={() => setCurrentQuizQuestionIndex(Math.min(quizQuestions.length - 1, activeQuizQuestionIndex + 1))}
                          disabled={activeQuizQuestionIndex >= quizQuestions.length - 1}
                          className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          Next <ChevronRight size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })() : null}
                {quizDisplayMode === "list" && savedQuizzes.length ? (
                  <div className="max-h-[34rem] space-y-3 overflow-y-auto pr-1">
                    {savedQuizzes.map((savedQuiz, index) => (
                      <div
                        key={savedQuiz.id}
                        className={`rounded-lg border p-4 ${
                          quiz?.id === savedQuiz.id
                            ? "border-blue-700/70 bg-blue-950/35"
                            : "border-slate-800 bg-slate-950/50"
                        }`}
                      >
                        <div className="mb-3 flex items-start justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-100">Quiz {savedQuizzes.length - index}</p>
                            <p className="mt-1 text-sm text-slate-400">
                              {savedQuiz.questions.length} questions · {formatSavedDate(savedQuiz.created_at)}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setQuiz(savedQuiz);
                              setCurrentQuizQuestionIndex(0);
                              setQuizDisplayMode("question");
                              setQuizSelections({});
                            }}
                            className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500"
                          >
                            Study
                          </button>
                        </div>
                        <div className="grid gap-2">
                          {savedQuiz.questions.slice(0, 3).map((questionItem, questionIndex) => (
                            <p key={questionItem.id} className="rounded-lg bg-slate-900/80 px-3 py-2 text-sm leading-6 text-slate-300 ring-1 ring-slate-800">
                              {questionIndex + 1}. {questionItem.prompt}
                            </p>
                          ))}
                          {savedQuiz.questions.length > 3 ? (
                            <p className="text-xs font-medium text-blue-200">
                              +{savedQuiz.questions.length - 3} more questions
                            </p>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
                {!quiz ? (
                  <p className="rounded-lg bg-slate-950/70 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
                    Generate a quiz or open past quizzes.
                  </p>
                ) : null}
                {quizDisplayMode === "list" && !savedQuizzes.length ? (
                  <p className="rounded-lg bg-slate-950/70 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
                    Past quizzes will appear here after you generate them.
                  </p>
                ) : null}
              </div>
            </>
          )}
        </div>

        <div className="grid gap-5">
          <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-5">
            <div className="mb-4 flex items-center gap-2">
              <BookOpen className="text-blue-300" size={20} />
              <h2 className="text-lg font-semibold">Weak areas</h2>
            </div>
            <div className="grid gap-3">
              {(weakTopics.length ? weakTopics : []).map((topic) => (
                <div key={topic.topic} className="rounded-lg bg-blue-950/35 p-3 ring-1 ring-blue-800/60">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-blue-100">{topic.topic}</p>
                    <span className="text-sm text-blue-200">{Math.round(topic.accuracy * 100)}%</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-blue-200/90">{topic.recommendation}</p>
                </div>
              ))}
              {!weakTopics.length ? (
                <p className="rounded-lg bg-slate-950/70 p-4 text-sm leading-6 text-slate-400 ring-1 ring-slate-800">
                  Missed quiz topics will shape your study plan.
                </p>
              ) : null}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-5">
            <div className="mb-4 flex items-center gap-2">
              <Shield className="text-blue-300" size={20} />
              <h2 className="text-lg font-semibold">Account safety</h2>
            </div>
            <form onSubmit={changePassword} className="grid gap-3">
              <label className="grid gap-2 text-sm font-medium text-slate-200">
                Current password
                <input
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  type="password"
                  autoComplete="current-password"
                  minLength={8}
                  maxLength={128}
                  className="focus-ring min-h-11 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-base text-slate-100 placeholder:text-slate-500"
                  placeholder="Current password"
                  required
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-slate-200">
                New password
                <input
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={128}
                  className="focus-ring min-h-11 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-base text-slate-100 placeholder:text-slate-500"
                  placeholder="8+ characters"
                  required
                />
              </label>
              <button
                disabled={busy === "password"}
                className="focus-ring inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white shadow-lg shadow-blue-950/40 hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <KeyRound size={17} /> {busy === "password" ? "Updating..." : "Change password"}
              </button>
            </form>

            <div className="mt-5 border-t border-slate-800 pt-5">
              <label className="grid gap-2 text-sm font-medium text-slate-200">
                Delete account confirmation
                <input
                  value={accountDeleteConfirmation}
                  onChange={(event) => setAccountDeleteConfirmation(event.target.value)}
                  type="text"
                  autoComplete="off"
                  className="focus-ring min-h-11 rounded-lg border border-red-900/70 bg-red-950/30 px-3 py-2 text-base text-red-50 placeholder:text-red-200/50"
                  placeholder="Type DELETE"
                />
              </label>
              <button
                type="button"
                onClick={deleteAccount}
                disabled={accountDeleteConfirmation !== "DELETE" || busy === "account-delete"}
                className="focus-ring mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-red-800 bg-red-950/70 px-4 py-2 font-semibold text-red-50 hover:border-red-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={17} /> {busy === "account-delete" ? "Deleting..." : "Delete account"}
              </button>
            </div>
          </div>

          {ENABLE_DEV_RAG ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <Layers3 className="text-blue-300" size={20} /> Dev RAG
                </h2>
                <button onClick={inspectRag} className="focus-ring rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-slate-100 hover:border-blue-500">
                  Inspect
                </button>
              </div>
              <div className="grid gap-3">
                {devChunks.map((chunk) => (
                  <div key={chunk.id} className="rounded-lg bg-slate-950 p-3 text-white ring-1 ring-blue-900/70">
                    <p className="flex items-center gap-2 text-sm font-semibold">
                      <Activity className="text-blue-300" size={16} /> {chunk.document_name} · {chunk.section} · {chunk.score.toFixed(2)}
                    </p>
                    <p className="mt-2 line-clamp-4 text-sm leading-6 text-slate-200">{chunk.text}</p>
                  </div>
                ))}
                {!devChunks.length ? <p className="text-sm text-slate-400">Retrieved chunks and scores appear here.</p> : null}
              </div>
            </div>
          ) : null}
        </div>
      </section>
        </main>
      </div>
    </>
  );
}
