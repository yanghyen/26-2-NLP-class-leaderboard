"use client";

import { ShieldAlert, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { useAuth } from "../../../../components/auth-provider";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader } from "../../../../components/ui";
import { useApiData } from "../../../../hooks/use-api-data";
import { api } from "../../../../lib/api";
import { formatDate } from "../../../../lib/format";

export default function QuarantinePage(){const{token}=useAuth();const loader=useCallback(()=>api.quarantine(token!),[token]);const{data,error,loading,refresh}=useApiData(loader,[loader]);const[actionError,setActionError]=useState<string|null>(null);async function remove(id:string){if(!window.confirm("격리 artifact를 영구 삭제할까요? 이 작업은 되돌릴 수 없습니다."))return;setActionError(null);try{await api.deleteArtifact(token!,id);await refresh()}catch(e){setActionError(e instanceof Error?e.message:"삭제하지 못했습니다.")}}if(loading)return <LoadingState/>;if(error||!data)return <ErrorState message={error??"격리 목록을 불러오지 못했습니다."} retry={refresh}/>;return <div className="space-y-6"><PageHeader title="Quarantine" description="보안 검사에서 격리된 제출입니다. 격리 파일은 UI에서 열거나 다운로드할 수 없습니다."/>{actionError&&<p className="text-sm text-red-700">{actionError}</p>}{data.length?<div className="overflow-x-auto border border-red-200 bg-white"><table><thead><tr><th>제출</th><th>사용자 ID</th><th>검사 상태</th><th>등록 시각</th><th>작업</th></tr></thead><tbody>{data.map(row=><tr key={row.id}><td><span className="inline-flex items-center gap-2 font-mono text-xs"><ShieldAlert className="h-4 w-4 text-red-700"/>{row.id}</span></td><td className="font-mono text-xs">{row.user_id}</td><td>{row.malware_scan_status||"검토 필요"}</td><td>{formatDate(row.created_at)}</td><td><Button variant="danger" onClick={()=>void remove(row.id)}><Trash2 className="h-4 w-4"/>영구 삭제</Button></td></tr>)}</tbody></table></div>:<EmptyState title="격리된 제출이 없습니다" description="현재 관리자 확인이 필요한 파일이 없습니다."/>}</div>}
