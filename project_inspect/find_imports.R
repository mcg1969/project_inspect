library_s = as.symbol("library")
colons_s = as.symbol("::")
walk.expr <- function(expr) {
    if (is.symbol(expr)) {
        result = c()
    } else if (expr[[1]] == library_s | expr[[1]] == colons_s) {
        result = c(toString(expr[[2]]))
    } else if (length(expr) == 1) {
        result = walk.expr(expr[[1]])
    } else {
        result = c()
        for (i in 1:length(expr)) {
            result = c(result, walk.expr(expr[[i]]))
        }
    }
    result
}
find.imports.string <- function(code) {
    walk.expr(parse(text=code))
}
find.imports.file <- function(fname) {
    walk.expr(parse(file=fname))
}
