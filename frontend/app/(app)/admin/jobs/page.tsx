"use client";

import { RefreshCw, RotateCcw } from "lucide-react";
import { useCallback, useState } from "react";
import { useAuth } from "../../../../components/auth-provider";
import { StatusBadge } from "../../../../components/status-badge";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader } from "../../../../components/ui";
import { useApiData } from "../../../../hooks/use-api-data";
import { api } from "../../../../lib/api";

const retryable=new Set(["EVALUATION_FAILED","QUEUE_UNAVAILABLE","SERVER_ERROR_RETRY"]);
export default function JobsPage(){const{token}=useAuth();const loader=useCallback(()=>api.jobs(token!),[token]);const{data,error,loading,refresh}=useApiData(loader,[loader]);const[actionError,setActionError]=useState<string|null>(null);async function retry(id:string){if(!window.confirm("이 평가 Job을 다시 대기열에 등록할까요?"))return;setActionError(null);try{await api.retryJob(token!,id);await refresh()}catch(e){setActionError(e instanceof Error?e.message:"재시도하지 못했습니다.")}}if(loading)return <LoadingState/>;if(error||!data)return <ErrorState message={error??"Job을 불러오지 못했습니다."} retry={refresh}/>;return <div className="space-y-6"><PageHeader title="Evaluation Jobs" description="평가 대기열과 실패 원인을 확인합니다. 학생 파일 오류는 관리자 재시도 대상이 아닙니다." action={<Button variant="secondary" onClick={()=>void refresh()}><RefreshCw className="h-4 w-4"/>새로고침</Button>}/>{actionError&&<p className="text-sm text-red-700">{actionError}</p>}{data.length?<div className="overflow-x-auto border border-zinc-200 bg-white"><table><thead><tr><th>Job ID</th><th>Submission</th><th>Split</th><th>상태</th><th>시도</th><th>Worker</th><th>오류</th><th>작업</th></tr></thead><tbody>{data.map(row=><tr key={row.id}><td className="font-mono text-xs">{row.id}</td><td className="font-mono text-xs">{row.submission_id}</td><td>{row.split}</td><td><StatusBadge status={row.status}/></td><td>{row.attempts}/{row.max_attempts}</td><td>{row.worker_id||"-"}</td><td>{row.safe_error_message||row.error_kind||"-"}</td><td>{row.status==="FAILED"&&row.error_kind&&retryable.has(row.error_kind)&&<Button variant="secondary" onClick={()=>void retry(row.id)}><RotateCcw className="h-4 w-4"/>재시도</Button>}</td></tr>)}</tbody></table></div>:<EmptyState title="평가 Job이 없습니다" description="평가 제출이 등록되면 이곳에 표시됩니다."/>}</div>}
