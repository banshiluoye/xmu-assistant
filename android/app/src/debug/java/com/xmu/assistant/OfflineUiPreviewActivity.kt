package com.xmu.assistant

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.time.LocalDate

/** Debug-only visual fixtures. Every API response is in-process; no real account or network. */
class OfflineUiPreviewActivity:ComponentActivity() {
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        val screen=intent.getStringExtra("screen") ?: "schedule"
        val mode=intent.getStringExtra("theme") ?: THEME_MODE_LIGHT
        setContent {
            XmuMobileTheme(mode) {
                val scope=rememberCoroutineScope()
                val task=remember {LearningTask("9","8","示例课程（离线预览）","实验报告 · Redis 集成","homework")}
                val transport=remember {QueryHttpTransport {request->
                    val body=when {
                        request.url.endsWith("/api/activities/9")->"""{"id":9,"course_id":8,"type":"homework","data":{"description":"<p>阅读实验说明，完成实现并提交实验报告。</p><p>支持 PDF、文档和照片附件。</p>"},"uploads":[{"id":3,"name":"实验要求.pdf"}]}"""
                        request.url.endsWith("/api/profile")->"""{"id":1}"""
                        request.url.endsWith("submission_list")->"""{"list":[]}"""
                        else->"{}"
                    }
                    QueryHttpResponse(request.url,200,null,body,emptyMap())
                }}
                val inbox=remember {LearningInboxState(applicationContext,"offline-ui-review","",scope,{},createClient={LearningClient("",transport)})}
                inbox.tasks=listOf(task,task.copy(id="10",title="本周在线测验",kind="exam"),task.copy(id="11",title="实验一 · 已交付",status="已提交"))
                Surface(Modifier.fillMaxSize(),color=MaterialTheme.colorScheme.background) {
                    Column(Modifier.fillMaxSize().systemBarsPadding().padding(horizontal=12.dp,vertical=6.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                        Text("虾大助手 · 离线预览",style=MaterialTheme.typography.titleMedium)
                        Box(Modifier.weight(1f)) {
                            when(screen) {
                                "todos"->LearningHub(inbox,emptyList(),true,45)
                                "requirements"->HomeworkFlow(inbox,task,false,{}, {})
                                "homework"->HomeworkFlow(inbox,task,true,{}, {})
                                else->{
                                    val today=LocalDate.now();val monday=today.minusDays(today.dayOfWeek.value-1L)
                                    val calendar=XmuAcademicCalendar("20261","2026-2027","第一学期",monday.minusWeeks(8),monday.plusWeeks(10))
                                    fun course(day:Int,start:Int,end:Int,name:String,room:String)=XmuScheduleEntry(day,start,end,scheduleSectionStartTime(start,800),scheduleSectionEndTime(end,2200),name,room,"示例教师","1-19周","20261")
                                    val rows=listOf(course(1,3,4,"计算机组成原理 A","坤銮楼 C304"),course(2,5,6,"马克思主义基本原理","学武楼 C305"),
                                        course(2,7,8,"计算机网络与通信","学武楼 A404"),course(3,5,6,"UNIX 系统程序设计","西部片区2号楼106"),
                                        course(4,1,2,"计算机网络与通信","学武楼 A404"),course(4,3,4,"计算机组成原理 A","坤銮楼 C304"),course(4,5,8,"计算机组成原理实验","西部片区4号楼301"),
                                        course(4,9,11,"学科实践","西部片区4号楼301"),course(5,1,4,"汇编语言程序设计 A","学武楼 A401"),course(5,5,6,"汇编语言程序设计 A","学武楼 A401"),
                                        course(5,9,11,"人工智能：机器学习","学武楼 A401"),course(7,11,12,"临时课程","学武楼 A101"))
                                    SchedulePage(rows,"20261",0,false,"",true,{},calendar,owner="offline-ui-review")
                                }
                            }
                        }
                        AppNavigationBar(if(screen=="schedule") "课表" else "学习待办",NotificationSettings(),0,{})
                    }
                }
            }
        }
    }
}
