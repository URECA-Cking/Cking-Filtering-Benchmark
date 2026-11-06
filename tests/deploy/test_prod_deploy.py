"""운영 배포 job: 올릴 이미지 정하기, 운영 Lambda 교체 순서 확인, 운영 태그 붙이기, 실패 시 이전 이미지로 되돌리기."""

import unittest

from tests.deploy.harness import SandboxTestCase

ECR = "551372961758.dkr.ecr.ap-northeast-2.amazonaws.com/cking-comment-filter"
FUNCTION = "prod-cking-comment-filter"
IMAGES_QUERY = "imageDetails[?imageTags].[imageDigest,join(` `,imageTags)]"
IMAGE_FILES = {
    "server/app.py": "app",
    "src/local_pipeline.py": "pipeline",
    "src/rules/decision.py": "rules",
    "requirements-server.txt": "fastapi",
    "requirements-image.txt": "torch",
    "Dockerfile": "FROM python",
    "model.sha256": "hash",
    ".dockerignore": "*",
    "scripts/build-image.sh": "build",
    "README.md": "readme",
    "src/train.py": "train",
}


def digest(n):
    return "sha256:" + str(n) * 64


NO_IMAGE = "::error::이 커밋과 이미지 내용이 같은 개발 이미지가 없다. develop의 개발 배포가 끝난 뒤 main에 합친다"


class PickProdImageTest(SandboxTestCase):
    def images(self, *rows):
        self.sb.on("ecr", "describe-images", IMAGES_QUERY, stdout="".join(f"{d}\t{' '.join(t)}\n" for d, t in rows))

    def run_step(self, sha, event="push", tag=""):
        return self.sb.run("pick-prod-image.sh", {
            "ECR_REPOSITORY": ECR, "GITHUB_SHA": sha, "GITHUB_EVENT_NAME": event, "INPUT_TAG": tag,
        })

    def test_내용이_같은_개발_이미지를_고른다(self):
        a = self.sb.commit(IMAGE_FILES)
        head = self.sb.commit({"README.md": "changed", "src/train.py": "changed"})
        self.images((digest(1), [a[:12]]))
        r = self.run_step(head)
        self.assertEqual(r.code, 0)
        self.assertEqual(r.outputs, {"digest": digest(1)})
        self.assertEqual(r.summary, f"올릴 이미지: 개발 커밋 {a[:12]} ({digest(1)})\n")

    def test_이미지_파일이_바뀌었는데_개발_이미지가_없으면_멈춘다(self):
        for changed in ("server/app.py", "src/local_pipeline.py", "src/rules/decision.py", "requirements-server.txt",
                        "Dockerfile", "model.sha256", ".dockerignore", "scripts/build-image.sh"):
            with self.subTest(changed=changed):
                a = self.sb.commit(IMAGE_FILES)
                head = self.sb.commit({changed: "changed " + changed})
                self.sb.rules.clear()
                self.images((digest(1), [a[:12]]))
                r = self.run_step(head)
                self.assertEqual(r.code, 1)
                self.assertIn(NO_IMAGE, r.stdout)
                self.assertEqual(r.outputs, {})

    def test_내용이_다른_갈라진_커밋_이미지는_고르지_않는다(self):
        a = self.sb.commit(IMAGE_FILES)
        self.sb.git("checkout", "-q", "-b", "other")
        other = self.sb.commit({"server/app.py": "other"})
        self.sb.git("checkout", "-q", "develop")
        head = self.sb.commit({"README.md": "changed"})
        self.images((digest(2), [other[:12]]), (digest(1), [a[:12]]))
        r = self.run_step(head)
        self.assertEqual(r.outputs, {"digest": digest(1)})

    def test_squash_릴리스는_내용이_같은_개발_이미지_중_최근_커밋을_고른다(self):
        base = self.sb.commit(IMAGE_FILES)
        self.sb.git("branch", "main")
        d1 = self.sb.commit({"server/app.py": "v2"})
        d2 = self.sb.commit({"README.md": "v2"})
        self.sb.git("checkout", "-q", "main")
        self.sb.git("checkout", d2, "--", ".")
        main = self.sb.commit(message="v1.0.0 (#1)")
        self.assertEqual(self.sb.git("merge-base", d2, main), base)
        self.images(
            (digest(2), [d2[:12]]),
            (digest(1), [d1[:12], f"prod-{d1[:12]}"]),
            (digest(0), [base[:12]]),
        )
        r = self.run_step(main)
        self.assertEqual(r.outputs, {"digest": digest(2)})
        self.assertEqual(r.summary, f"올릴 이미지: 개발 커밋 {d2[:12]} ({digest(2)})\n")

    def test_prod_태그와_이력에_없는_커밋_태그는_보지_않는다(self):
        a = self.sb.commit(IMAGE_FILES)
        self.images((digest(3), ["0123456789ab", f"prod-{a[:12]}", "latest"]), (digest(1), [a[:12]]))
        r = self.run_step(a)
        self.assertEqual(r.outputs, {"digest": digest(1)})

    def test_내용이_같은_개발_이미지가_없으면_멈춘다(self):
        a = self.sb.commit(IMAGE_FILES)
        self.images((digest(3), [f"prod-{a[:12]}"]))
        r = self.run_step(a)
        self.assertEqual(r.code, 1)
        self.assertIn(NO_IMAGE, r.stdout)

    def test_이미지_목록_조회_실패는_aws_오류로_멈춘다(self):
        a = self.sb.commit(IMAGE_FILES)
        self.sb.on("ecr", "describe-images", stderr="An error occurred (AccessDeniedException)\n", code=254)
        r = self.run_step(a)
        self.assertEqual(r.code, 254)
        self.assertNotIn("::error::", r.stdout)
        self.assertEqual(r.outputs, {})

    def test_수동_실행은_태그_형식을_검사한다(self):
        a = self.sb.commit(IMAGE_FILES)
        for tag in ("", a[:12], "prod-" + a[:11], "prod-" + a[:12].upper(), "prod-" + a[:13]):
            with self.subTest(tag=tag):
                r = self.run_step(a, "workflow_dispatch", tag)
                self.assertEqual(r.code, 1)
                self.assertIn(f"::error::태그는 prod-<커밋 12자리>다: {tag}", r.stdout)
                self.assertEqual(r.calls, [])

    def test_수동_실행은_고른_운영_태그를_그대로_쓴다(self):
        a = self.sb.commit(IMAGE_FILES)
        tag = "prod-0123456789ab"
        self.sb.on("ecr", "describe-images", f"imageTag={tag}", stdout=digest(4) + "\n")
        r = self.run_step(a, "workflow_dispatch", tag)
        self.assertEqual(r.code, 0)
        self.assertEqual(r.outputs, {"digest": digest(4)})
        self.assertEqual(r.summary, f"수동 되돌리기: {tag} ({digest(4)})\n")

    def test_수동_실행_태그가_없으면_aws_오류로_멈춘다(self):
        a = self.sb.commit(IMAGE_FILES)
        self.sb.on("ecr", "describe-images", stderr="An error occurred (ImageNotFoundException)\n", code=254)
        r = self.run_step(a, "workflow_dispatch", "prod-0123456789ab")
        self.assertEqual(r.code, 254)
        self.assertEqual(r.outputs, {})


CURRENT = digest(9)


class CheckProdOrderTest(SandboxTestCase):
    def setUp(self):
        super().setUp()
        self.old = self.sb.commit({"server/app.py": "1"})
        self.head = self.sb.commit({"server/app.py": "2"})
        self.newer = self.sb.commit({"server/app.py": "3"})
        self.sb.git("checkout", "-q", "-b", "other", self.old)
        self.diverged = self.sb.commit({"server/app.py": "other"})
        self.sb.git("checkout", "-q", "develop")

    def deployed(self, *tags):
        self.sb.on("lambda", "get-function", stdout=f"{ECR}@{CURRENT}\n")
        self.sb.on("ecr", "describe-images", f"imageDigest={CURRENT}", stdout="\t".join(tags) + "\n")

    def run_step(self, event="push"):
        return self.sb.run("check-prod-order.sh", {
            "ECR_REPOSITORY": ECR, "PROD_FUNCTION_NAME": FUNCTION, "GITHUB_SHA": self.head, "GITHUB_EVENT_NAME": event,
        })

    def test_운영_Lambda가_없으면_건너뛴다(self):
        self.sb.on("lambda", "get-function", stderr="An error occurred (ResourceNotFoundException)\n", code=254)
        r = self.run_step()
        self.assertEqual(r.code, 0)
        self.assertEqual(r.outputs, {"skip": "true"})
        self.assertEqual(r.summary, "운영 Lambda가 아직 없어 건너뛴다\n")

    def test_Lambda_조회_오류는_멈춘다(self):
        err = "An error occurred (AccessDeniedException)\n"
        self.sb.on("lambda", "get-function", stderr=err, code=254)
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(err, r.stdout)
        self.assertEqual(r.outputs, {})

    def test_수동_되돌리기는_순서를_보지_않는다(self):
        self.deployed(f"prod-{self.newer[:12]}")
        r = self.run_step("workflow_dispatch")
        self.assertEqual(r.code, 0)
        self.assertEqual(r.outputs, {"previous": CURRENT})
        self.assertEqual(r.aws("ecr"), [])

    def test_처음_이미지는_prod_태그가_없어도_진행한다(self):
        self.deployed(self.old[:12])
        r = self.run_step()
        self.assertEqual(r.code, 0)
        self.assertEqual(r.outputs, {"previous": CURRENT})

    def test_배포된_운영_커밋이_조상이거나_같으면_진행한다(self):
        for tags in ((f"prod-{self.old[:12]}",), (f"prod-{self.head[:12]}",), (f"prod-{self.old[:12]}", f"prod-{self.head[:12]}")):
            with self.subTest(tags=tags):
                self.sb.rules.clear()
                self.deployed(*tags)
                r = self.run_step()
                self.assertEqual(r.code, 0)
                self.assertEqual(r.outputs, {"previous": CURRENT})

    def test_더_새_운영_커밋이면_건너뛴다(self):
        self.deployed(self.newer[:12], f"prod-{self.newer[:12]}")
        r = self.run_step()
        msg = f"더 새 커밋 {self.newer[:12]} 이 운영에 배포되어 있어 건너뛴다"
        self.assertEqual(r.code, 0)
        self.assertIn(f"::warning::{msg}", r.stdout)
        self.assertEqual(r.summary, msg + "\n")
        self.assertEqual(r.outputs, {"previous": CURRENT, "skip": "true"})

    def test_갈라진_운영_커밋이면_멈춘다(self):
        self.deployed(f"prod-{self.diverged[:12]}")
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(f"::error::배포된 운영 커밋 {self.diverged[:12]} 과 이 커밋의 이력이 갈라졌다", r.stdout)

    def test_이력에_없는_운영_커밋이면_멈춘다(self):
        self.deployed("prod-0123456789ab")
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(f"::error::배포된 운영 이미지 {ECR}@{CURRENT} 의 커밋을 확인할 수 없다", r.stdout)

    def test_배포된_이미지_ECR_조회_실패는_멈춘다(self):
        self.sb.on("lambda", "get-function", stdout=f"{ECR}@{CURRENT}\n")
        self.sb.on("ecr", "describe-images", stderr="An error occurred (ThrottlingException)\n", code=254)
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(f"::error::배포된 운영 이미지 {ECR}@{CURRENT} 의 태그를 조회하지 못했다", r.stdout)
        self.assertNotIn("skip", r.outputs)


DIGEST = digest(5)
MEDIA_QUERY = "images[0].imageManifestMediaType"
MANIFEST_QUERY = "images[0].imageManifest"
MANIFEST = '{"schemaVersion":2,"mediaType":"application/vnd.oci.image.manifest.v1+json"}'


class TagProdImageTest(SandboxTestCase):
    def setUp(self):
        super().setUp()
        self.sha = self.sb.commit({"server/app.py": "1"})
        self.tag = f"prod-{self.sha[:12]}"

    def run_step(self):
        return self.sb.run("tag-prod-image.sh", {"ECR_REPOSITORY": ECR, "GITHUB_SHA": self.sha, "DIGEST": DIGEST})

    def test_이미_같은_이미지에_붙어_있으면_그대로_둔다(self):
        self.sb.on("ecr", "describe-images", f"imageTag={self.tag}", stdout=DIGEST + "\n")
        r = self.run_step()
        self.assertEqual(r.code, 0)
        self.assertEqual(r.aws("put-image"), [])

    def test_다른_이미지에_붙어_있으면_멈춘다(self):
        self.sb.on("ecr", "describe-images", f"imageTag={self.tag}", stdout=digest(6) + "\n")
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(f"::error::{self.tag} 가 다른 이미지({digest(6)})에 붙어 있다", r.stdout)
        self.assertEqual(r.aws("put-image"), [])

    def new_tag(self, put_error=None):
        self.sb.on("ecr", "describe-images", stderr="An error occurred (ImageNotFoundException)\n", code=254)
        self.sb.on("ecr", "batch-get-image", MEDIA_QUERY, stdout="application/vnd.oci.image.manifest.v1+json\n")
        self.sb.on("ecr", "batch-get-image", MANIFEST_QUERY, stdout=MANIFEST + "\n")
        if put_error:
            self.sb.on("ecr", "put-image", stderr=put_error, code=254)
        else:
            self.sb.on("ecr", "put-image", stdout=self.tag + "\n")

    def test_새_태그는_받은_매니페스트_그대로_고른_digest에_붙인다(self):
        self.new_tag()
        r = self.run_step()
        self.assertEqual(r.code, 0)
        self.assertEqual(r.aws("put-image"), [[
            "ecr", "put-image", "--repository-name", "cking-comment-filter", "--image-tag", self.tag,
            "--image-manifest", MANIFEST, "--image-manifest-media-type", "application/vnd.oci.image.manifest.v1+json",
            "--image-digest", DIGEST, "--query", "image.imageId.imageTag", "--output", "text",
        ]])
        self.assertEqual(r.stdout, self.tag + "\n")

    def test_digest가_다르면_ECR이_거부해_멈춘다(self):
        self.new_tag("An error occurred (ImageDigestDoesNotMatchException)\n")
        r = self.run_step()
        self.assertEqual(r.code, 254)
        self.assertIn("ImageDigestDoesNotMatchException", r.stderr)


PREVIOUS = digest(7)
NEW = digest(8)


class RollbackProdLambdaTest(SandboxTestCase):
    def state(self, status, image, wait_code=0):
        self.sb.on("lambda", "wait", "function-updated-v2", code=wait_code,
                   stderr="Waiter FunctionUpdatedV2 failed: Max attempts exceeded\n" if wait_code else "")
        self.sb.on("lambda", "get-function", stdout=f"{status}\t{ECR}@{image}\n")
        self.sb.on("lambda", "update-function-code", stdout="InProgress\n")

    def run_step(self):
        return self.sb.run("rollback-prod-lambda.sh", {"ECR_REPOSITORY": ECR, "PROD_FUNCTION_NAME": FUNCTION, "PREVIOUS": PREVIOUS})

    def assert_rolled_back(self, r):
        self.assertEqual(r.code, 0)
        self.assertEqual(r.aws("update-function-code"), [[
            "lambda", "update-function-code", "--function-name", FUNCTION,
            "--image-uri", f"{ECR}@{PREVIOUS}", "--query", "LastUpdateStatus", "--output", "text",
        ]])
        self.assertEqual(len(r.aws("wait")), 2)
        self.assertIn(f"::error::교체 또는 확인에 실패해 이전 이미지({PREVIOUS})로 되돌렸다", r.stdout)

    def test_이미지가_그대로면_되돌리지_않는다(self):
        self.state("Successful", PREVIOUS)
        r = self.run_step()
        self.assertEqual(r.code, 0)
        self.assertIn(f"::error::이미지 교체가 적용되지 않아 이전 이미지({PREVIOUS}) 그대로다", r.stdout)
        self.assertEqual(r.aws("update-function-code"), [])

    def test_교체가_Failed면_되돌린다(self):
        self.state("Failed", NEW)
        self.assert_rolled_back(self.run_step())

    def test_확인_실패면_되돌린다(self):
        self.state("Successful", NEW)
        self.assert_rolled_back(self.run_step())

    def test_아직_교체_중이면_되돌리지_못하고_실패한다(self):
        self.state("InProgress", NEW, wait_code=255)
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(f"::error::이미지 교체가 아직 진행 중이라 되돌리지 못했다. 끝난 뒤 이전 이미지({PREVIOUS})로 되돌린다", r.stdout)
        self.assertEqual(r.aws("update-function-code"), [])


if __name__ == "__main__":
    unittest.main()
