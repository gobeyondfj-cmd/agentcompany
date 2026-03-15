"""Tests for the Task model and TaskBoard."""

from __future__ import annotations

from agent_company_ai.core.task import Task, TaskBoard, TaskStatus


class TestTaskLifecycle:
    """Test task state transitions."""

    def test_create_unassigned(self):
        task = Task.create(description="Test task")
        assert task.status == TaskStatus.PENDING
        assert task.assignee is None
        assert task.result is None

    def test_create_assigned(self):
        task = Task.create(description="Test task", assignee="alice")
        assert task.status == TaskStatus.ASSIGNED
        assert task.assignee == "alice"

    def test_assign(self):
        task = Task.create(description="Test task")
        task.assign("bob")
        assert task.status == TaskStatus.ASSIGNED
        assert task.assignee == "bob"

    def test_start(self):
        task = Task.create(description="Test task", assignee="alice")
        task.start()
        assert task.status == TaskStatus.IN_PROGRESS

    def test_complete(self):
        task = Task.create(description="Test task", assignee="alice")
        task.start()
        task.complete("Done!")
        assert task.status == TaskStatus.DONE
        assert task.result == "Done!"

    def test_fail(self):
        task = Task.create(description="Test task", assignee="alice")
        task.start()
        task.fail("Something went wrong")
        assert task.status == TaskStatus.FAILED
        assert task.result == "Something went wrong"

    def test_cancel(self):
        task = Task.create(description="Test task")
        task.cancel("No longer needed")
        assert task.status == TaskStatus.CANCELLED
        assert task.result == "No longer needed"


class TestTerminal:
    """Test is_terminal property."""

    def test_pending_not_terminal(self):
        task = Task.create(description="Test")
        assert not task.is_terminal

    def test_done_is_terminal(self):
        task = Task.create(description="Test")
        task.complete("ok")
        assert task.is_terminal

    def test_failed_is_terminal(self):
        task = Task.create(description="Test")
        task.fail("err")
        assert task.is_terminal

    def test_cancelled_is_terminal(self):
        task = Task.create(description="Test")
        task.cancel()
        assert task.is_terminal


class TestSubtasks:
    """Test subtask management."""

    def test_add_subtask(self):
        task = Task.create(description="Parent")
        sub = task.add_subtask("Child task")
        assert sub.parent_id == task.id
        assert len(task.subtasks) == 1

    def test_all_subtasks_done_empty(self):
        task = Task.create(description="Parent")
        assert task.all_subtasks_done is True

    def test_all_subtasks_done_mixed(self):
        task = Task.create(description="Parent")
        sub1 = task.add_subtask("Sub 1")
        sub2 = task.add_subtask("Sub 2")
        sub1.complete("ok")
        assert task.all_subtasks_done is False
        sub2.complete("ok")
        assert task.all_subtasks_done is True


class TestToDict:
    """Test serialization."""

    def test_to_dict_keys(self):
        task = Task.create(description="Test", assignee="alice")
        d = task.to_dict()
        assert d["description"] == "Test"
        assert d["assignee"] == "alice"
        assert d["status"] == "assigned"
        assert "id" in d
        assert "created_at" in d


class TestTaskBoard:
    """Test the TaskBoard."""

    def test_add_and_get(self):
        board = TaskBoard()
        task = Task.create(description="Test")
        board.add(task)
        assert board.get(task.id) is task

    def test_get_nonexistent(self):
        board = TaskBoard()
        assert board.get("nope") is None

    def test_remove(self):
        board = TaskBoard()
        task = Task.create(description="Test")
        board.add(task)
        board.remove(task.id)
        assert board.get(task.id) is None

    def test_list_all(self):
        board = TaskBoard()
        t1 = Task.create(description="Task 1")
        t2 = Task.create(description="Task 2")
        board.add(t1)
        board.add(t2)
        assert len(board.list_all()) == 2

    def test_list_by_status(self):
        board = TaskBoard()
        t1 = Task.create(description="T1")
        t2 = Task.create(description="T2", assignee="alice")
        board.add(t1)
        board.add(t2)
        pending = board.list_by_status(TaskStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].id == t1.id

    def test_list_by_assignee(self):
        board = TaskBoard()
        t1 = Task.create(description="T1", assignee="alice")
        t2 = Task.create(description="T2", assignee="bob")
        board.add(t1)
        board.add(t2)
        alice_tasks = board.list_by_assignee("alice")
        assert len(alice_tasks) == 1

    def test_summary(self):
        board = TaskBoard()
        board.add(Task.create(description="T1"))
        board.add(Task.create(description="T2", assignee="alice"))
        s = board.summary()
        assert s.get("pending", 0) == 1
        assert s.get("assigned", 0) == 1

    def test_pending_tasks(self):
        board = TaskBoard()
        board.add(Task.create(description="T1"))
        board.add(Task.create(description="T2", assignee="alice"))
        t3 = Task.create(description="T3")
        t3.complete("done")
        board.add(t3)
        pending = board.pending_tasks()
        assert len(pending) == 2

    def test_active_tasks(self):
        board = TaskBoard()
        t = Task.create(description="T1", assignee="alice")
        t.start()
        board.add(t)
        assert len(board.active_tasks()) == 1
