package com.xmu.assistant

import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.time.Instant

class LearningClientTest {
    @Test fun `camera attachment larger than four MiB streams separate storage blocks without school cookies`() {
        val file=java.io.File.createTempFile("camera-fixture-",".jpg")
        try {
            val bytes=ByteArray(4*1024*1024+3){1};bytes[bytes.lastIndex]=9;file.writeBytes(bytes)
            val api=QueryHttpTransport {request->QueryHttpResponse(request.url,200,null,
                if(request.url.endsWith("/api/uploads")) """{"id":7,"upload_url":"https://storage.invalid","storage_type":"QINIU"}""" else """{"uptoken":"fixture"}""",emptyMap())}
            val lengths=mutableListOf<Long>();var joined=""
            val client=LearningClient("private-school-cookie",api,storageTransport={request->
                assertNull(request.header("Cookie"))
                val buffer=okio.Buffer();requireNotNull(request.body).writeTo(buffer)
                if("/mkblk/" in request.url.encodedPath){if(buffer.size==3L) assertEquals(9,buffer.clone().readByteArray().last().toInt());lengths+=buffer.size;"""{"ctx":"block${lengths.size}"}"""}
                else {joined=buffer.readUtf8();"{}"}
            })
            assertEquals(7,client.upload(file).getInt("id"))
            assertEquals(listOf(4194304L,3L),lengths);assertEquals("block1,block2",joined)
        } finally {file.delete()}
    }
    private val task=LearningTask("9","8","课程","作业","homework")
    @Test fun `empty rich text stays empty and genuine media is preserved`() {
        listOf("", "<p><br></p>","<p>&nbsp;\u200b</p>","<style>p{}</style><div>\n</div>").forEach {assertEquals("",meaningfulLearningHtml(it))}
        assertTrue(meaningfulLearningHtml("<p>答案</p>").isNotEmpty())
        assertTrue(meaningfulLearningHtml("<img src=\"https://example.test/image.png\">").isNotEmpty())
    }
    @Test fun `deadline filters default to future and undated but overdue is available`() {
        val now=Instant.parse("2026-11-07T05:00:00Z")
        val old=task.copy(deadline="2026-11-06T10:00:00+08:00")
        val future=task.copy(id="10",deadline="2026-11-08T10:00:00+08:00")
        assertEquals(listOf(future,task),filterLearningTasks(listOf(old,task,future),"","","全部状态","未过期","",now))
        assertEquals(listOf(old),filterLearningTasks(listOf(old,task,future),"","","全部状态","已逾期","",now))
    }
    @Test fun `attachment only submission sends one file and no generated pdf or empty html`() {
        var writes=0;var submitted=false
        var payload=JSONObject()
        val transport=QueryHttpTransport {request->
            val body=when {
                request.method=="POST" -> {writes++;payload=JSONObject(request.body);submitted=true;"{}"}
                request.url.endsWith("/api/activities/9") -> """{"id":9,"course_id":8,"type":"homework","is_started":true}"""
                request.url.endsWith("/api/profile") -> """{"id":1}"""
                request.url.endsWith("submission_list") -> """{"list":[]}"""
                submitted -> """{"id":2,"is_draft":false,"comment":"","uploads":[{"id":5,"name":"report.pdf"}]}"""
                else -> "{}"
            }
            QueryHttpResponse(request.url,200,null,body,emptyMap())
        }
        LearningClient("fixture",transport).submit(task,"<p><br></p>",listOf(JSONObject("""{"id":5,"name":"report.pdf"}"""),JSONObject("""{"id":99,"source":"auto-generated-pdf"}""")),false)
        assertEquals(1,writes);assertEquals("",payload.getString("comment"));assertEquals(1,payload.getJSONArray("uploads").length());assertEquals(5,payload.getJSONArray("uploads").getInt(0))
    }
    @Test fun `uncertain submission reads back and never retries the write`() {
        var writes=0
        val transport=QueryHttpTransport {request->
            if(request.method=="POST"){writes++;throw java.io.IOException("timeout")}
            val body=when {request.url.endsWith("/api/activities/9")->"""{"course_id":8,"type":"homework"}""";request.url.endsWith("/api/profile")->"""{"id":1}""";else->"{}"}
            QueryHttpResponse(request.url,200,null,body,emptyMap())
        }
        assertThrows(LearningSubmissionUncertain::class.java){LearningClient("fixture",transport).submit(task,"<p>答案</p>",emptyList(),false)}
        assertEquals(1,writes)
    }
}
